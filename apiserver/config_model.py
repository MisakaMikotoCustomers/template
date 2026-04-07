#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置模型定义 - 使用 dataclass 映射配置文件
"""

from dataclasses import dataclass, field
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 及以下


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    url_prefix: str = ""


@dataclass
class DatabaseConfig:
    """数据库配置（MySQL）"""
    type: str = "mysql"
    url: str = "127.0.0.1"
    port: int = 3306
    username: str = "root"
    password: str = ""
    database: str = "shop"

    def get_connection_url(self) -> str:
        return f"mysql+pymysql://{self.username}:{self.password}@{self.url}:{self.port}/{self.database}"


@dataclass
class AlipayConfig:
    """支付宝配置"""
    app_id: str = ""
    app_private_key: str = ""      # RSA2 私钥（PKCS8 格式，不含头尾）
    alipay_public_key: str = ""    # 支付宝公钥（不含头尾）
    notify_url: str = ""           # 异步通知回调 URL（公网可访问）
    return_url: str = ""           # 同步返回 URL（支付完成后跳转）
    gateway: str = "https://openapi.alipay.com/gateway.do"
    sandbox: bool = False          # 沙箱模式


@dataclass
class OssConfig:
    """对象存储配置（腾讯云 COS）"""
    enabled: bool = False
    secret_id: str = ""
    secret_key: str = ""
    region: str = "ap-guangzhou"
    bucket: str = ""
    base_url: str = ""             # 公开访问域名前缀，如 https://xxx.cos.ap-guangzhou.myqcloud.com


@dataclass
class AppConfig:
    """应用总配置"""
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    alipay: AlipayConfig = field(default_factory=AlipayConfig)
    oss: OssConfig = field(default_factory=OssConfig)
    admin_token: str = ""  # 管理员静态 Token

    @classmethod
    def from_toml(cls, path: str) -> "AppConfig":
        """从 TOML 文件加载配置"""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls(
            server=ServerConfig(**data.get("server", {})),
            database=DatabaseConfig(**data.get("database", {})),
            alipay=AlipayConfig(**data.get("alipay", {})),
            oss=OssConfig(**data.get("oss", {})),
            admin_token=data.get("admin_token", ""),
        )
