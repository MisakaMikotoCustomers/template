#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
腾讯云 APM（应用性能监控）接入工具 —— FastAPI 版

与 ai_task/apiserver/utils/apm_utils.py 设计同构，但为适配 template 项目的
FastAPI + async SQLAlchemy + httpx 栈，做如下替换：

- instrument_flask → instrument_fastapi（opentelemetry-instrumentation-fastapi）
- instrument_requests → instrument_httpx（opentelemetry-instrumentation-httpx）
- SQLAlchemyInstrumentor 传入 AsyncEngine 时需要 engine.sync_engine

职责：
- 基于 OpenTelemetry + OTLP 协议将 trace 上报到腾讯云 APM
- enabled=False 时完全跳过，零开销；SDK 未就绪或初始化失败时降级 warning
- 实例标识按 HOST_HOSTNAME / CONTAINER_NAME 环境变量组合，避免 APM 控制台 "unknown"
- 接入约定与腾讯云「接入应用」→「外网上报」一致：
  * ``https://<region>.apm.tencentcs.com:4320`` —— TLS 上的 OTLP/gRPC（控制台 HTTPS 接入点）
  * ``http://<region>.apm.tencentcs.com:4319``  —— 明文 OTLP/gRPC（控制台 HTTP 接入点）
  两个接入点都是 gRPC，必须配 ``[apm].protocol = "grpc"``；若配成 "http"，
  OTLPSpanExporter(proto/http) 会把请求打到 gRPC 端口，服务端直接 `RemoteDisconnected`
  断开，span 永远上报不出去。``_coerce_otlp_endpoint_protocol`` 针对历史误配
  （endpoint 为 ``*.apm.tencentcs.com`` 但 protocol="http"）会自动纠正到 grpc，
  并记一条 warning。
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


class _LoggingSpanExporterWrapper:
    """把 OTLP exporter 的每次导出结果显式打日志，便于排障。

    OTel 内部 BatchSpanProcessor 只在失败时用 `opentelemetry.sdk._shared_internal`
    logger 打 ERROR，成功不吭声。真排障时我们需要"每批次导出了几条、成功还是失败、
    哪条返回码"的事实。包一层即可。
    """

    def __init__(self, inner, label: str = 'OTLP'):
        self._inner = inner
        self._label = label
        self._ok_batches = 0
        self._ok_spans = 0
        self._fail_batches = 0

    def export(self, spans):
        from opentelemetry.sdk.trace.export import SpanExportResult
        n = len(spans)
        sample_name = spans[0].name if spans else ''
        try:
            result = self._inner.export(spans)
        except Exception as exc:
            self._fail_batches += 1
            logger.exception(
                'APM %s export raised: spans=%d first=%r fail_batches=%d: %s',
                self._label, n, sample_name, self._fail_batches, exc,
            )
            return SpanExportResult.FAILURE
        if result == SpanExportResult.SUCCESS:
            self._ok_batches += 1
            self._ok_spans += n
            logger.info(
                'APM %s export OK: spans=%d first=%r ok_batches=%d ok_spans=%d',
                self._label, n, sample_name, self._ok_batches, self._ok_spans,
            )
        else:
            self._fail_batches += 1
            logger.warning(
                'APM %s export FAILURE result=%s spans=%d first=%r fail_batches=%d',
                self._label, result, n, sample_name, self._fail_batches,
            )
        return result

    def shutdown(self):
        return self._inner.shutdown()

    # OTLP exporter 可能还被查 force_flush；直通。
    def force_flush(self, timeout_millis: int = 30000):
        fn = getattr(self._inner, 'force_flush', None)
        if callable(fn):
            return fn(timeout_millis)
        return True


def _resolve_host_identity() -> tuple[str, str]:
    """解析上报到 APM 的主机/实例标识。

    组合规则（优先级从高到低）：
    1. HOST_HOSTNAME + CONTAINER_NAME → "{HOST_HOSTNAME}.{CONTAINER_NAME}"
    2. 仅 HOST_HOSTNAME → "{HOST_HOSTNAME}.{container_id}"
    3. 仅 CONTAINER_NAME → "{CONTAINER_NAME}"
    4. 兜底：容器自身 hostname（docker 默认 = 容器短 ID 12 位）

    Returns:
        (host_name, instance_id)
    """
    server_host = (os.environ.get('HOST_HOSTNAME') or '').strip()
    container_name = (os.environ.get('CONTAINER_NAME') or '').strip()
    container_id = (socket.gethostname() or 'unknown').strip()

    if server_host and container_name:
        host_name = f'{server_host}.{container_name}'
    elif server_host:
        host_name = f'{server_host}.{container_id}'
    elif container_name:
        host_name = container_name
    else:
        host_name = container_id

    instance_id = f'{host_name}:{os.getpid()}'
    return host_name, instance_id


def _coerce_otlp_endpoint_protocol(endpoint: str, protocol: str) -> tuple[str, str]:
    """规范化 OTLP 接入点与协议组合。

    - 腾讯云 APM 外网 ``:4319/:4320`` 都是 gRPC（``https://`` 仅代表 TLS），必须配 protocol=grpc。
      若用户对 ``*.apm.tencentcs.com`` 配了 protocol=http，本函数会 **自动纠正为 grpc**
      并记 warning（保留 http 的唯一结局就是 `RemoteDisconnected`，自动纠正反而能立刻恢复上报）。
    - 自建 OpenTelemetry Collector 通常走 OTLP/HTTP，空路径的会补全到 ``/v1/traces``。
    """
    ep = (endpoint or '').strip()
    proto = (protocol or 'http').strip().lower()
    if proto not in ('grpc', 'http'):
        proto = 'http'

    if ep.startswith('https://') or ep.startswith('http://'):
        parsed = urlparse(ep)
        host = (parsed.hostname or '').lower()
        is_tencent_apm = host.endswith('.apm.tencentcs.com')
        if is_tencent_apm and proto == 'http':
            logger.warning(
                'APM：endpoint=%s 指向腾讯云 APM（:4319/:4320 均为 OTLP/gRPC），'
                'protocol 配成 "http" 会被服务端 RemoteDisconnected。已自动切换到 grpc；'
                '请把 [apm].protocol 改成 "grpc" 以消除此警告。', ep,
            )
            proto = 'grpc'
        if proto == 'grpc':
            return proto, ep
        path = (parsed.path or '').strip()
        if path in ('', '/'):
            ep = urlunparse(parsed._replace(path='/v1/traces'))
            logger.info('APM OTLP/HTTP 接入点已补全路径: %s', ep)
        return proto, ep

    if proto == 'http':
        logger.warning(
            'APM protocol=http 但 endpoint 无 http(s) scheme（%s）；导出可能失败，请检查配置。',
            ep[:80],
        )
    return proto, ep


def init_apm(apm_config, app: Any = None, engine: Any = None) -> bool:
    """根据 ApmConfig 初始化 OpenTelemetry 并接入腾讯云 APM。

    Args:
        apm_config: ApmConfig 实例
        app: FastAPI app；启用 instrument_fastapi 时需要
        engine: SQLAlchemy AsyncEngine；启用 instrument_sqlalchemy 时需要
                内部会取 engine.sync_engine 传给 SQLAlchemyInstrumentor

    Returns:
        True: 初始化成功并已挂载 exporter
        False: 跳过（未启用 / 配置缺失 / SDK 不可用 / 出错）
    """
    if apm_config is None or not getattr(apm_config, 'enabled', False):
        return False

    if not apm_config.token:
        logger.warning('APM token 未配置，跳过 APM 初始化')
        return False
    if not apm_config.endpoint:
        logger.warning('APM endpoint 未配置，跳过 APM 初始化')
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError as e:
        logger.warning('OpenTelemetry SDK 未就绪，跳过 APM 初始化: %s', e)
        return False

    eff_proto, eff_endpoint = _coerce_otlp_endpoint_protocol(
        getattr(apm_config, 'endpoint', '') or '',
        getattr(apm_config, 'protocol', 'http') or 'http',
    )

    try:
        if eff_proto == 'http':
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError as e:
        logger.warning('OTLP exporter 未就绪（protocol=%s），跳过 APM 初始化: %s', eff_proto, e)
        return False

    try:
        host_name, instance_id = _resolve_host_identity()

        # 腾讯云 APM 要求 Resource 中携带 token；同时 header 也传一遍，提高兼容性
        resource = Resource.create({
            'service.name': apm_config.service_name,
            'service.instance.id': instance_id,
            'deployment.environment': apm_config.env,
            'host.name': host_name,
            'host.id': host_name,
            'token': apm_config.token,
        })
        sampler = TraceIdRatioBased(rate=apm_config.sampler_ratio)
        provider = TracerProvider(resource=resource, sampler=sampler)

        # OTLP 鉴权 header key 必须**全小写**。gRPC/HTTP2 metadata key 语法只允许
        # [-_.0-9a-z]+，Python grpc 客户端在发送前会强校验，含任何大写字母直接抛
        # "metadata was invalid: ('Authentication', ...)" —— span 根本出不了本机。
        # 腾讯云 APM 端对 key 大小写不敏感，小写就行。
        exporter_kwargs = {
            'endpoint': eff_endpoint,
            'headers': (('authentication', apm_config.token),),
        }
        if eff_proto == 'grpc':
            # https:// + gRPC 走 TLS（与腾讯云文档一致）；裸 host:port 为明文 gRPC
            if not eff_endpoint.startswith('https://'):
                exporter_kwargs['insecure'] = True
        exporter = OTLPSpanExporter(**exporter_kwargs)
        logger.info(
            'APM OTLP exporter built: protocol=%s endpoint=%s insecure=%s headers_keys=%s',
            eff_proto, eff_endpoint,
            exporter_kwargs.get('insecure'),
            [k for k, _ in exporter_kwargs.get('headers', ())],
        )
        # 用 wrapper 包一层，每批导出的成功/失败都显式打日志，避免只靠 OTel 内部的 ERROR
        # 事件做判断（成功时 OTel 完全静默，排障时无法确定 exporter 是否真跑了）
        wrapped_otlp = _LoggingSpanExporterWrapper(inner=exporter, label='OTLP')
        provider.add_span_processor(BatchSpanProcessor(span_exporter=wrapped_otlp))

        # 排障期默认同时挂 ConsoleSpanExporter，和 OTLP 并行（对齐腾讯官方文档示例
        # `--traces_exporter=console,otlp_proto_grpc` 的思路），`docker logs` 可直接
        # 看到 span 的 resource / attributes / status 等实际内容，验证是否包含旧
        # semconv（http.method / http.target / http.status_code）。需要关掉时设环境
        # 变量 OTEL_DEBUG_SPAN_CONSOLE=0（或 off/false/no）。
        console_off_values = {'0', 'false', 'no', 'off'}
        if os.environ.get('OTEL_DEBUG_SPAN_CONSOLE', '').strip().lower() not in console_off_values:
            try:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
                logger.info('APM ConsoleSpanExporter enabled (set OTEL_DEBUG_SPAN_CONSOLE=0 to disable)')
            except Exception as e:
                logger.warning('APM ConsoleSpanExporter 挂载失败: %s', e)
        else:
            logger.info('APM ConsoleSpanExporter disabled (OTEL_DEBUG_SPAN_CONSOLE=%s)',
                        os.environ.get('OTEL_DEBUG_SPAN_CONSOLE', ''))

        trace.set_tracer_provider(provider)
        logger.info(
            'APM TracerProvider set: service.name=%s service.instance.id=%s host.name=%s '
            'deployment.environment=%s sampler=TraceIdRatioBased(%.2f)',
            apm_config.service_name, instance_id, host_name,
            apm_config.env, apm_config.sampler_ratio,
        )
    except Exception as e:
        logger.exception('APM TracerProvider 初始化失败: %s', e)
        return False

    # FastAPI 自动埋点
    if apm_config.instrument_fastapi and app is not None:
        # 腾讯云 APM 的「应用 / 接口分析」聚合仍然按旧 HTTP semconv（http.method / http.target /
        # http.status_code）抽字段。opentelemetry-instrumentation-fastapi >= 0.46b0 默认只发新
        # 的稳定语义（http.request.method / url.path / http.response.status_code），导致链路
        # 追踪有数据但接口分析是空的。
        # 解决：opt-in 到 dup 模式，同时吐两套 attribute，新旧消费者兼容。该 env 必须在
        # 导入 FastAPIInstrumentor 之前设置（相关模块在 import 时读一次）。
        os.environ.setdefault('OTEL_SEMCONV_STABILITY_OPT_IN', 'http/dup')
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
            logger.info('APM FastAPIInstrumentor attached (semconv_opt_in=%s)',
                        os.environ.get('OTEL_SEMCONV_STABILITY_OPT_IN', ''))
        except Exception as e:
            logger.warning('FastAPIInstrumentor 挂载失败，跳过: %s', e)

    # SQLAlchemy 自动埋点：AsyncEngine 需取 sync_engine 传入
    if apm_config.instrument_sqlalchemy and engine is not None:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            sync_engine = getattr(engine, 'sync_engine', None) or engine
            SQLAlchemyInstrumentor().instrument(engine=sync_engine)
            logger.info('APM SQLAlchemyInstrumentor attached')
        except Exception as e:
            logger.warning('SQLAlchemyInstrumentor 挂载失败，跳过: %s', e)

    # httpx 自动埋点（用于外部 HTTP 调用）
    if apm_config.instrument_httpx:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
            logger.info('APM HTTPXClientInstrumentor attached')
        except Exception as e:
            logger.warning('HTTPXClientInstrumentor 挂载失败，跳过: %s', e)

    logger.info(
        'APM initialized: service=%s instance=%s host=%s env=%s endpoint=%s protocol=%s sampler_ratio=%.2f',
        apm_config.service_name, instance_id, host_name, apm_config.env,
        eff_endpoint, eff_proto, apm_config.sampler_ratio,
    )
    return True
