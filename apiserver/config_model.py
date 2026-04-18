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
class SpecialAccountConfig:
    """特殊账号（内置/保留账号）：启动时按 name 对齐 user 表，自动成为注册黑名单。"""
    name: str = ""
    # 明文密码。启动时会用 SHA-256 哈希后写入 user.password_hash，
    # 与前端登录提交的 password_hash（浏览器端 SHA-256）保持同一编码。
    password: str = ""


@dataclass
class AuthConfig:
    """鉴权相关配置"""
    session_expire_days: int = 7
    # 特殊账号列表：
    # - name 集合会作为注册黑名单（大小写不敏感）
    # - 启动时会自动 upsert 到 user 表（password → SHA-256）
    # - 默认至少保留一个 admin；为空也允许，但会失去管理端登录入口
    special_accounts: List[SpecialAccountConfig] = field(default_factory=list)


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
        auth_raw = dict(data.get("auth") or {})
        # special_accounts 在 TOML 中是 [[auth.special_accounts]]，即 list[dict]；
        # 要手动转成 dataclass 实例，否则 AuthConfig(**auth_raw) 会塞一堆 dict 进去
        raw_accounts = auth_raw.pop("special_accounts", []) or []
        accounts = [
            SpecialAccountConfig(
                name=str(item.get("name") or ""),
                password=str(item.get("password") or ""),
            )
            for item in raw_accounts
            if isinstance(item, dict)
        ]
        return cls(
            server=ServerConfig(**data.get("server", {})),
            database=DatabaseConfig(**data.get("database", {})),
            auth=AuthConfig(**auth_raw, special_accounts=accounts),
        )

    @classmethod
    def load(cls) -> "AppConfig":
        """按统一规则加载配置（env > default path）。"""
        path = resolve_config_path()
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        return cls.from_toml(path)
