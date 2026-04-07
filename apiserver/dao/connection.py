#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLAlchemy 数据库连接管理
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from config_model import DatabaseConfig

_engine = None
_session_factory = None
_scoped_session = None


def init_connection(config: DatabaseConfig):
    """初始化数据库连接池"""
    global _engine, _session_factory, _scoped_session

    if config.type != "mysql":
        raise ValueError(f"Unsupported database type: {config.type}")

    connection_url = (
        f"mysql+pymysql://{config.username}:{config.password}"
        f"@{config.url}:{config.port}/{config.database}?charset=utf8mb4"
    )

    _engine = create_engine(
        connection_url,
        echo=False,
        pool_size=20,
        max_overflow=40,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
        connect_args={"init_command": "SET SESSION time_zone='+00:00'"}
    )

    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    _scoped_session = scoped_session(_session_factory)

    print(f"Database engine initialized: {config.url}:{config.port}/{config.database}")


def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_connection first.")
    return _engine


def get_session() -> Session:
    if _scoped_session is None:
        raise RuntimeError("Database not initialized. Call init_connection first.")
    return _scoped_session()


def remove_session():
    if _scoped_session is not None:
        _scoped_session.remove()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """上下文管理器形式获取 Session，自动提交/回滚"""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
