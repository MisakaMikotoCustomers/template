#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一日志工具（template apiserver 侧）

与 ai-task apiserver 版本的差异：
- 本模板是 FastAPI（async），用 `contextvars.ContextVar` 承载每请求上下文，
  替换掉原版的 `threading.local` + Flask `request` 读取路径；
- 其余（JsonFormatter / 脱敏 / 截断 / init_logging）保持一致。

职责：
- JSON 结构化 formatter：输出固定 schema，必带 ts(UTC)/level/trace_id/user_id
- 敏感关键词脱敏（Authorization/Bearer/password/token/secret_key/access_key 等）
- ContextVar 承载 trace_id / user_id / path / method 等请求级字段
- `init_logging()` 入口：挂 stdout + 可选 AsyncCLSHandler（cls.enabled=True 才挂）
- `bind_context()`：给调度线程 / 非 HTTP 路径手动打字段
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import socket
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# 敏感字段正则：按关键词 + 等号/冒号分隔形式掩码
_SENSITIVE_PATTERNS = [
    (re.compile(r'(?i)(authorization\s*:\s*bearer\s+)\S+'), r'\1***'),
    (re.compile(r'(?i)(authorization\s*:\s*)\S+'), r'\1***'),
    (re.compile(r'(?i)(password\s*[=:]\s*)\S+'), r'\1***'),
    (re.compile(r'(?i)(passwd\s*[=:]\s*)\S+'), r'\1***'),
    (re.compile(r'(?i)(token\s*[=:]\s*)[A-Za-z0-9\-_.+/=]{6,}'), r'\1***'),
    (re.compile(r'(?i)(secret[_-]?key\s*[=:]\s*)\S+'), r'\1***'),
    (re.compile(r'(?i)(access[_-]?key\s*[=:]\s*)\S+'), r'\1***'),
    (re.compile(r'(?i)(private[_-]?key\s*[=:]\s*)\S+'), r'\1***'),
    (re.compile(r'(?i)(x-client-secret\s*[=:]\s*)\S+'), r'\1***'),
]

_MAX_MSG_BYTES = 64 * 1024  # 单条 msg 截断上限（UTF-8 字节）


def _mask(text: str) -> str:
    if not text:
        return text
    result = text
    for pattern, repl in _SENSITIVE_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def _truncate_msg(msg: str) -> tuple[str, bool]:
    encoded = msg.encode('utf-8', errors='replace')
    if len(encoded) <= _MAX_MSG_BYTES:
        return msg, False
    return encoded[:_MAX_MSG_BYTES].decode('utf-8', errors='ignore'), True


# 每请求上下文：FastAPI 中间件 / 调度器显式打点
_request_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'log_request_context', default=None,
)


def bind_context(**fields: Any) -> contextvars.Token:
    """
    绑定当前协程的日志上下文字段。返回 Token，调用方可 `reset_context(token)` 还原。

    常用字段：trace_id / user_id / path / method / status / latency_ms / event /
              client_id / task_id / chat_id / message_id。
    """
    current = dict(_request_context.get() or {})
    current.update({k: v for k, v in fields.items() if v is not None})
    return _request_context.set(current)


def reset_context(token: contextvars.Token) -> None:
    """配合 `bind_context` 返回的 token 还原上下文（请求结束时调用）。"""
    try:
        _request_context.reset(token)
    except (ValueError, LookupError):
        # token 已失效（跨协程传递等边界）——退化为清空，不抛异常
        _request_context.set({})


def get_context() -> Dict[str, Any]:
    return dict(_request_context.get() or {})


def clear_context() -> None:
    _request_context.set({})


class JsonFormatter(logging.Formatter):
    """输出固定 schema 的 JSON；必带 ts/level/trace_id/user_id。"""

    def __init__(self, service: str, env: str, host_id: str):
        super().__init__()
        self.service = service
        self.env = env
        self.host_id = host_id

    def format(self, record: logging.LogRecord) -> str:
        try:
            raw_msg = record.getMessage()
        except Exception as e:
            raw_msg = f'<msg_format_error: {e}>'
        masked = _mask(raw_msg)
        truncated_msg, truncated = _truncate_msg(masked)

        payload: Dict[str, Any] = {
            'ts': datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec='milliseconds')
            .replace('+00:00', 'Z'),
            'level': record.levelname,
            'service': self.service,
            'env': self.env,
            'host_id': self.host_id,
            'module': record.name,
            'file': record.filename,
            'line': record.lineno,
            'msg': truncated_msg,
        }

        extra_trace = getattr(record, 'trace_id', None)
        extra_user = getattr(record, 'user_id', None)
        ctx = get_context()

        # 优先级：LogRecord.extra > ContextVar（request 中间件写入） > 空串
        payload['trace_id'] = extra_trace or ctx.get('trace_id') or ''
        payload['user_id'] = str(extra_user or ctx.get('user_id') or '')

        # 其余可选上下文：只要任一来源有就带出
        for key in ('client_id', 'task_id', 'chat_id', 'message_id', 'path', 'method',
                    'status', 'latency_ms', 'event'):
            value = getattr(record, key, None)
            if value is None:
                value = ctx.get(key)
            if value is not None:
                payload[key] = value

        if truncated:
            payload['truncated'] = True

        if record.exc_info:
            try:
                payload['exception'] = _mask(self.formatException(record.exc_info))
            except Exception:
                payload['exception'] = '<exception_format_error>'

        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return json.dumps({'ts': payload['ts'], 'level': payload['level'], 'msg': '<json_dump_error>'})


def _build_host_id() -> str:
    hostname = socket.gethostname() or 'unknown'
    return f'{hostname}:{os.getpid()}'


def init_logging(
    cls_config,
    service: str,
    env: str,
    host_id: Optional[str] = None,
    topic_id: Optional[str] = None,
    credential_provider=None,
    level: int = logging.INFO,
) -> None:
    """
    初始化日志：挂 stdout JSON handler；若 cls_config.enabled 则挂 AsyncCLSHandler。

    参数:
        cls_config: ClsConfig 实例（dataclass）；若 enabled=False 只挂 stdout
        service: 服务标识（apiserver 等）
        env: 环境（prod / test / default）
        host_id: 主机标识，None 时自动生成 "hostname:pid"
        topic_id: 覆盖 cls_config.topic_id_apiserver
        credential_provider: 自定义凭证提供者（静态/STS），None 时用 cls_config 静态 AK
        level: 日志级别，默认 INFO
    """
    resolved_host_id = host_id or _build_host_id()
    formatter = JsonFormatter(service=service, env=env, host_id=resolved_host_id)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.setLevel(level)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(level)
    root.addHandler(stdout_handler)

    if cls_config is None or not getattr(cls_config, 'enabled', False):
        return

    try:
        from utils.cls_handler import AsyncCLSHandler, StaticCredentialProvider
    except ImportError:
        root.warning('cls_handler 未就绪，跳过 CLS 远程上报 handler 挂载')
        return

    effective_topic = topic_id or getattr(cls_config, 'topic_id', '')
    if not effective_topic:
        root.warning('CLS topic_id 未配置，跳过远程上报 handler 挂载')
        return

    provider = credential_provider or StaticCredentialProvider(
        secret_id=cls_config.secret_id,
        secret_key=cls_config.secret_key,
    )
    try:
        cls_handler = AsyncCLSHandler(
            region=cls_config.region,
            topic_id=effective_topic,
            credential_provider=provider,
            fallback_path=cls_config.fallback_path,
            fallback_max_mb=cls_config.fallback_max_mb,
        )
    except Exception as e:
        root.error('AsyncCLSHandler 初始化失败，跳过远程上报: %s', e)
        return

    cls_handler.setFormatter(formatter)
    cls_handler.setLevel(level)
    root.addHandler(cls_handler)
    root.info('CLS handler mounted: service=%s env=%s topic_id=%s region=%s',
              service, env, effective_topic, cls_config.region)
