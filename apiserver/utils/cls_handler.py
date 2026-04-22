#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
腾讯云 CLS 异步日志上报 Handler

职责：
- 作为 logging.Handler 使用；emit 仅入队，后台线程批量 PushLog
- 失败降级：写本地 fallback.jsonl（带大小轮转，避免写爆磁盘）
- 支持静态 AK 与 STS 临时凭证两种凭证提供方式
- 进程退出时尽量 flush 剩余数据

依赖：腾讯云 CLS 日志上报 SDK —— `tencentcloud-cls-sdk-python`
（注意：不是 `tencentcloud-sdk-python-cls`，那是管理 API 的 SDK，没有日志上报接口）
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple


class _RateLimitedStderr:
    """限流 stderr 打印，避免 CLS 故障时自身日志风暴。"""

    def __init__(self, min_interval_seconds: int = 30):
        self._min_interval = min_interval_seconds
        self._last_emit = 0.0
        self._lock = threading.Lock()

    def emit(self, msg: str) -> None:
        with self._lock:
            now = time.time()
            if now - self._last_emit < self._min_interval:
                return
            self._last_emit = now
        try:
            sys.stderr.write(msg.rstrip() + '\n')
            sys.stderr.flush()
        except Exception:
            pass


_stderr = _RateLimitedStderr()


@dataclass
class CredentialSnapshot:
    """凭证快照（静态或 STS）。"""
    secret_id: str
    secret_key: str
    token: str = ''          # STS 临时凭证需要的 token；静态 AK 为空
    expired_at: int = 0      # Unix 秒；0 表示不过期


class CredentialProvider:
    """凭证提供者基类。"""

    def get(self) -> CredentialSnapshot:
        raise NotImplementedError


class StaticCredentialProvider(CredentialProvider):
    """静态 SecretId/Key（apiserver 侧用）。"""

    def __init__(self, secret_id: str, secret_key: str):
        self._snapshot = CredentialSnapshot(secret_id=secret_id, secret_key=secret_key)

    def get(self) -> CredentialSnapshot:
        return self._snapshot


class CallableCredentialProvider(CredentialProvider):
    """回调式凭证提供者（clients 侧：指向 config.cls，随 STS 刷新自动生效）。"""

    def __init__(self, loader: Callable[[], CredentialSnapshot]):
        self._loader = loader

    def get(self) -> CredentialSnapshot:
        return self._loader()


class FallbackFile:
    """本地降级文件，按大小轮转。"""

    def __init__(self, path: str, max_mb: int = 200):
        self._path = path
        self._max_bytes = max(1, max_mb) * 1024 * 1024
        self._lock = threading.Lock()
        directory = os.path.dirname(path) or '.'
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception:
            pass

    def write_many(self, lines: List[str]) -> None:
        if not lines:
            return
        with self._lock:
            try:
                self._rotate_if_needed()
                with open(self._path, 'a', encoding='utf-8') as f:
                    for line in lines:
                        f.write(line)
                        if not line.endswith('\n'):
                            f.write('\n')
            except Exception as e:
                _stderr.emit(f'[cls-handler] fallback write failed: {e}')

    def _rotate_if_needed(self) -> None:
        try:
            if os.path.exists(self._path) and os.path.getsize(self._path) >= self._max_bytes:
                backup = f'{self._path}.1'
                try:
                    if os.path.exists(backup):
                        os.remove(backup)
                except Exception:
                    pass
                os.replace(self._path, backup)
        except Exception:
            pass


class AsyncCLSHandler(logging.Handler):
    """异步批量上报 CLS 的 logging.Handler。"""

    _shutdown_timeout_seconds = 3.0

    def __init__(
        self,
        region: str,
        topic_id: str,
        credential_provider: CredentialProvider,
        fallback_path: str,
        fallback_max_mb: int = 200,
        max_queue: int = 10000,
        batch_size: int = 200,
        flush_interval_ms: int = 1000,
    ):
        super().__init__()
        self.region = region
        self.topic_id = topic_id
        self.credential_provider = credential_provider
        self.batch_size = batch_size
        self.flush_interval_ms = flush_interval_ms
        self.fallback = FallbackFile(path=fallback_path, max_mb=fallback_max_mb)

        self._queue: queue.Queue[Tuple[float, str]] = queue.Queue(maxsize=max_queue)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, name='cls-upload-worker', daemon=True)
        self._worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self.format(record)
        except Exception as e:
            _stderr.emit(f'[cls-handler] format failed: {e}')
            return
        try:
            self._queue.put_nowait((record.created, payload))
        except queue.Full:
            self.fallback.write_many([payload])

    def close(self) -> None:
        self._stop_event.set()
        try:
            self._worker.join(timeout=self._shutdown_timeout_seconds)
        except Exception:
            pass
        super().close()

    def _run(self) -> None:
        buffer: List[Tuple[float, str]] = []
        last_flush = time.time()
        while not self._stop_event.is_set():
            timeout_s = max(0.05, self.flush_interval_ms / 1000.0)
            try:
                item = self._queue.get(timeout=timeout_s)
                buffer.append(item)
            except queue.Empty:
                pass

            now = time.time()
            flush_due = (now - last_flush) * 1000.0 >= self.flush_interval_ms
            if buffer and (len(buffer) >= self.batch_size or flush_due):
                self._upload(buffer)
                buffer = []
                last_flush = now

        # 退出前最后一次 flush
        while True:
            try:
                buffer.append(self._queue.get_nowait())
            except queue.Empty:
                break
            if len(buffer) >= self.batch_size:
                self._upload(buffer)
                buffer = []
        if buffer:
            self._upload(buffer)

    def _upload(self, batch: List[Tuple[float, str]]) -> None:
        try:
            cred = self.credential_provider.get()
        except Exception as e:
            _stderr.emit(f'[cls-handler] credential fetch failed: {e}')
            self.fallback.write_many([payload for _, payload in batch])
            return

        try:
            self._push_to_cls(cred=cred, batch=batch)
        except Exception as e:
            _stderr.emit(f'[cls-handler] CLS upload failed: {e}')
            self.fallback.write_many([payload for _, payload in batch])

    def _push_to_cls(self, cred: CredentialSnapshot, batch: List[Tuple[float, str]]) -> None:
        """
        通过专用 CLS 上报 SDK 的 put_log_raw 接口写入。
        SDK 内部会做 protobuf 序列化 + lz4 压缩 + 签名。
        """
        try:
            from tencentcloud.log.logclient import LogClient
            from tencentcloud.log.cls_pb2 import LogGroupList
        except ImportError as e:
            raise RuntimeError(
                'tencentcloud-cls-sdk-python or a required module is missing: %s' % e
            ) from e

        endpoint = f'https://{self.region}.cls.tencentcs.com'
        client = LogClient(
            endpoint,
            cred.secret_id,
            cred.secret_key,
            securityToken=cred.token or None,
            region=self.region,
            is_https=True,
        )

        log_group_list = LogGroupList()
        log_group = log_group_list.logGroupList.add()
        log_group.source = ''
        for ts, payload in batch:
            log_entry = log_group.logs.add()
            # CLS Log.time 单位是秒（Unix timestamp）
            log_entry.time = int(ts)
            for kv in _json_to_contents(payload):
                content = log_entry.contents.add()
                content.key = kv['key']
                content.value = kv['value']

        client.put_log_raw(self.topic_id, log_group_list)


def _json_to_contents(payload: str) -> List[Dict[str, str]]:
    """把一条 JSON 日志拆成 CLS 的 Contents(key-value) 列表；解析失败则整条塞进 msg 字段。"""
    try:
        obj = json.loads(payload)
        if not isinstance(obj, dict):
            return [{'key': 'msg', 'value': payload}]
        return [{'key': str(k), 'value': _stringify(v)} for k, v in obj.items()]
    except Exception:
        return [{'key': 'msg', 'value': payload}]


def _stringify(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)
