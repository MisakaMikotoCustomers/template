#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web 前端服务配置模型
"""

from dataclasses import dataclass, field
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8081
    url_prefix: str = ""


@dataclass
class ApiServerConfig:
    host: str = "http://localhost:8080"
    path_prefix: str = "/api"


@dataclass
class WebConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    apiserver: ApiServerConfig = field(default_factory=ApiServerConfig)
    business: bool = True   # 是否开启商业化功能（商品购买等）

    @classmethod
    def from_toml(cls, path: str) -> "WebConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            server=ServerConfig(**data.get("server", {})),
            apiserver=ApiServerConfig(**data.get("apiserver", {})),
            business=data.get("business", True),
        )
