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
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any

logger = logging.getLogger(__name__)


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

    try:
        if apm_config.protocol == 'http':
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError as e:
        logger.warning('OTLP exporter 未就绪（protocol=%s），跳过 APM 初始化: %s', apm_config.protocol, e)
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

        exporter_kwargs = {
            'endpoint': apm_config.endpoint,
            'headers': (('authentication', apm_config.token),),
        }
        if apm_config.protocol == 'grpc':
            # 腾讯云 APM gRPC 接入点不需要 TLS（明文 token 鉴权）
            exporter_kwargs['insecure'] = True
        exporter = OTLPSpanExporter(**exporter_kwargs)
        provider.add_span_processor(BatchSpanProcessor(span_exporter=exporter))
        trace.set_tracer_provider(provider)
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
        except Exception as e:
            logger.warning('FastAPIInstrumentor 挂载失败，跳过: %s', e)

    # SQLAlchemy 自动埋点：AsyncEngine 需取 sync_engine 传入
    if apm_config.instrument_sqlalchemy and engine is not None:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            sync_engine = getattr(engine, 'sync_engine', None) or engine
            SQLAlchemyInstrumentor().instrument(engine=sync_engine)
        except Exception as e:
            logger.warning('SQLAlchemyInstrumentor 挂载失败，跳过: %s', e)

    # httpx 自动埋点（用于外部 HTTP 调用）
    if apm_config.instrument_httpx:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
        except Exception as e:
            logger.warning('HTTPXClientInstrumentor 挂载失败，跳过: %s', e)

    logger.info(
        'APM initialized: service=%s instance=%s host=%s env=%s endpoint=%s protocol=%s sampler_ratio=%.2f',
        apm_config.service_name, instance_id, host_name, apm_config.env,
        apm_config.endpoint, apm_config.protocol, apm_config.sampler_ratio,
    )
    return True
