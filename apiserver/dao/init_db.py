#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库初始化 - 创建所有表
"""

from config_model import DatabaseConfig
from .connection import init_connection, get_engine
from .models import Base


def init_database(config: DatabaseConfig):
    """初始化数据库连接并创建表"""
    init_connection(config)
    Base.metadata.create_all(get_engine())
    print("Database tables initialized.")
