#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLAlchemy 2.0 async 连接管理（aiomysql）

- 全局一个 AsyncEngine + async_sessionmaker
- 通过 get_db_session() async context manager 获取会话
- 所有 DAO 必须使用 async/await，避免阻塞事件循环
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config_model import DatabaseConfig

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def init_engine(config: DatabaseConfig) -> AsyncEngine:
    """创建全局 AsyncEngine。幂等。"""
    global _engine, _session_maker
    if _engine is not None:
        return _engine

    if config.type != "mysql":
        raise ValueError(f"暂不支持的数据库类型: {config.type}，请使用 mysql")

    _engine = create_async_engine(
        config.async_url(),
        echo=config.echo,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_recycle=config.pool_recycle,
        pool_pre_ping=True,
        future=True,
    )
    _session_maker = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("数据库未初始化，请先调用 init_engine()")
    return _engine


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """统一的异步 Session 上下文管理器。

    - 正常退出 commit
    - 异常回滚并抛出
    """
    if _session_maker is None:
        raise RuntimeError("数据库未初始化，请先调用 init_engine()")

    session = _session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """优雅关停 engine（FastAPI shutdown 调用）。"""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
