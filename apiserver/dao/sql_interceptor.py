#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLAlchemy SQL 执行拦截器：统一打印每条 SQL 的耗时，超过阈值则结构化上报。

与 ai-task 版本的差异：
- 本模板使用 SQLAlchemy 2.0 **async engine**（`AsyncEngine`），底层事件钩子
  要挂在 `engine.sync_engine` 上，否则 `event.listens_for(async_engine, ...)`
  不会匹配到实际 `_DBAPICursorCompat` 的 execute 事件。

实现要点：
- 通过 `conn.info['_query_start_time']` 堆栈暂存开始时间（允许嵌套连接）。
- 每条 SQL 都以 INFO 级别打印；<阈值 event=mysql.query，>=阈值 event=mysql.slow，
  便于下游按 event 聚合或告警。
- 参数值默认打印（log_params=True），方便排查；设为 False 只打印 params_count。
- SQL 文本统一截断到 `max_sql_bytes`，参数单独截断到 `max_params_bytes`。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger('template.mysql_slow')

_DEFAULT_SLOW_THRESHOLD_MS = 200
_DEFAULT_MAX_SQL_BYTES = 2048
_DEFAULT_MAX_PARAMS_BYTES = 1024
_STATEMENT_TYPES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'ALTER', 'DROP')


def install_sql_interceptor(
    engine,
    slow_threshold_ms: int = _DEFAULT_SLOW_THRESHOLD_MS,
    max_sql_bytes: int = _DEFAULT_MAX_SQL_BYTES,
    log_params: bool = True,
    max_params_bytes: int = _DEFAULT_MAX_PARAMS_BYTES,
) -> None:
    """
    把 SQL 执行拦截器挂到给定的 SQLAlchemy Engine（同步或 Async 均可）。
    幂等：已挂则跳过。

    对 `AsyncEngine` 实际监听的是其底层 `sync_engine`；对同步 `Engine` 直接监听。

    Args:
        engine: SQLAlchemy Engine / AsyncEngine 实例
        slow_threshold_ms: 超过该毫秒数的 SQL 以 event=mysql.slow 标记；其余用 event=mysql.query
        max_sql_bytes: SQL 文本截断上限（UTF-8 字节）
        log_params: 是否在日志里打印参数值（默认 True）；为 False 时仅打印 params_count
        max_params_bytes: 参数字典渲染后的截断长度（UTF-8 字节）
    """
    target_engine = getattr(engine, 'sync_engine', engine)
    if getattr(target_engine, '_sql_interceptor_installed', False):
        logger.debug('sql_interceptor already installed on engine, skip')
        return

    try:
        from sqlalchemy import event
    except ImportError:
        logger.warning('SQLAlchemy event API 不可用，跳过 SQL 拦截器安装')
        return

    threshold_ms = max(0, int(slow_threshold_ms))

    @event.listens_for(target_engine, 'before_cursor_execute')
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        stack = conn.info.setdefault('_query_start_time', [])
        stack.append(time.monotonic())

    @event.listens_for(target_engine, 'after_cursor_execute')
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        stack = conn.info.get('_query_start_time') or []
        if not stack:
            return
        started = stack.pop()
        duration_ms = int((time.monotonic() - started) * 1000)

        sql_preview = _truncate(statement or '', max_sql_bytes)
        statement_type = _detect_statement_type(sql_preview)
        params_count = _count_params(parameters=parameters, executemany=executemany)
        rowcount = _safe_rowcount(cursor)
        is_slow = duration_ms >= threshold_ms

        extra = {
            'event': 'mysql.slow' if is_slow else 'mysql.query',
            'sql': sql_preview,
            'statement_type': statement_type,
            'duration_ms': duration_ms,
            'params_count': params_count,
            'rowcount': rowcount,
            'executemany': bool(executemany),
        }

        if log_params:
            params_preview = _format_params(
                parameters=parameters,
                executemany=executemany,
                max_bytes=max_params_bytes,
            )
            extra['params'] = params_preview
            logger.info(
                'mysql %s type=%s duration_ms=%d sql=%s params=%s',
                'slow' if is_slow else 'query', statement_type, duration_ms, sql_preview, params_preview,
                extra=extra,
            )
        else:
            logger.info(
                'mysql %s type=%s duration_ms=%d sql=%s',
                'slow' if is_slow else 'query', statement_type, duration_ms, sql_preview,
                extra=extra,
            )

    target_engine._sql_interceptor_installed = True
    logger.info(
        'sql_interceptor installed: slow_threshold_ms=%d log_params=%s',
        threshold_ms, log_params,
    )


def _truncate(text: str, max_bytes: int) -> str:
    try:
        encoded = text.encode('utf-8', errors='replace')
    except Exception:
        return text[:max_bytes]
    if len(encoded) <= max_bytes:
        return ' '.join(text.split())
    return encoded[:max_bytes].decode('utf-8', errors='ignore') + '...'


def _detect_statement_type(sql: str) -> str:
    head = sql.lstrip().upper()[:16]
    for token in _STATEMENT_TYPES:
        if head.startswith(token):
            return token
    return 'OTHER'


def _count_params(parameters, executemany: bool) -> int:
    if parameters is None:
        return 0
    try:
        if executemany and isinstance(parameters, (list, tuple)):
            return len(parameters)
        if isinstance(parameters, dict):
            return len(parameters)
        if isinstance(parameters, (list, tuple)):
            return len(parameters)
    except Exception:
        return 0
    return 0


def _safe_rowcount(cursor) -> Optional[int]:
    try:
        rc = getattr(cursor, 'rowcount', None)
        if rc is None or rc < 0:
            return None
        return int(rc)
    except Exception:
        return None


def _format_params(parameters: Any, executemany: bool, max_bytes: int) -> str:
    if parameters is None:
        return ''
    try:
        if executemany and isinstance(parameters, (list, tuple)):
            rendered = repr(list(parameters[:3]))
            if len(parameters) > 3:
                rendered = f'{rendered} ...+{len(parameters) - 3} more'
        else:
            rendered = repr(parameters)
    except Exception as e:
        return f'<unrenderable: {e!r}>'
    return _truncate(rendered, max_bytes)
