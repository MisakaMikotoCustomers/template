#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DAO 包初始化：暴露数据库生命周期入口。"""

from config_model import DatabaseConfig
from .connection import dispose_engine, get_db_session, init_engine
from .models import Base


async def init_database(config: DatabaseConfig) -> None:
    """初始化数据库连接 + 自动建表。"""
    engine = init_engine(config)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


__all__ = [
    "init_database",
    "dispose_engine",
    "get_db_session",
]
