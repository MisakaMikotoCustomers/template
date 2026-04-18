#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置模型定义 - 使用 dataclass 映射 TOML 配置文件

启动时优先读取环境变量 APP_CONFIG_PATH 指定的路径，
否则回退到 /config/config.toml。
"""

import os
from dataclasses import dataclass, field
from typing import List

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 及以下


DEFAULT_CONFIG_PATH = "/config/config.toml"


def resolve_config_path() -> str:
    """统一的配置文件路径解析：APP_CONFIG_PATH 环境变量优先。"""
    return os.environ.get("APP_CONFIG_PATH", DEFAULT_CONFIG_PATH)


@dataclass
class ServerConfig:
    """HTTP 服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    url_prefix: str = ""          # URL 前缀，例如 "/v1"，为空不加前缀
    workers: int = 1              # uvicorn/gunicorn 进程数；I/O 场景单进程 + 协程池足矣
    log_level: str = "info"


@dataclass
class DatabaseConfig:
    """数据库配置（MySQL + 异步驱动）"""
    type: str = "mysql"                   # 目前仅支持 mysql
    url: str = "127.0.0.1"                # 数据库地址
    port: int = 3306
    username: str = "root"
    password: str = ""
    database: str = "template"
    pool_size: int = 20
    max_overflow: int = 10
    pool_recycle: int = 3600
    echo: bool = False

    def async_url(self) -> str:
        """SQLAlchemy 2.0 + aiomysql 的异步连接串。"""
        if self.type != "mysql":
            raise ValueError(f"暂不支持的数据库类型: {self.type}")
        return (
            f"mysql+aiomysql://{self.username}:{self.password}"
            f"@{self.url}:{self.port}/{self.database}?charset=utf8mb4"
        )


@dataclass
class AuthConfig:
    """鉴权相关配置"""
    session_expire_days: int = 7
    # 注册黑名单：以下用户名（大小写不敏感，完全匹配）禁止被注册
    username_blacklist: List[str] = field(default_factory=lambda: ["admin"])


@dataclass
class AppConfig:
    """应用总配置"""
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    @classmethod
    def from_toml(cls, path: str) -> "AppConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            server=ServerConfig(**data.get("server", {})),
            database=DatabaseConfig(**data.get("database", {})),
            auth=AuthConfig(**data.get("auth", {})),
        )

    @classmethod
    def load(cls) -> "AppConfig":
        """按统一规则加载配置（env > default path）。"""
        path = resolve_config_path()
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        return cls.from_toml(path)
