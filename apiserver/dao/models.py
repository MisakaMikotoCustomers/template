#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM 模型定义
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    Numeric, Index, func, BigInteger
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def to_iso_utc(dt: datetime):
    """统一将 datetime 序列化为 UTC ISO8601 字符串"""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class User(Base):
    """用户表"""
    __tablename__ = 'shop_users'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, comment='用户名')
    password_hash = Column(String(256), nullable=False, comment='密码哈希')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.utc_timestamp(),
                        onupdate=func.utc_timestamp(), comment='更新时间')

    __table_args__ = (
        Index('uk_users_username', 'username', unique=True),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'created_at': to_iso_utc(self.created_at),
        }


class UserSession(Base):
    """用户会话表"""
    __tablename__ = 'shop_user_sessions'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    token = Column(String(255), nullable=False, comment='Token')
    expires_at = Column(DateTime, nullable=False, comment='过期时间')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')

    __table_args__ = (
        Index('uk_sessions_token', 'token', unique=True),
        Index('idx_sessions_user_id', 'user_id'),
    )


class Product(Base):
    """商品表"""
    __tablename__ = 'shop_products'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    key = Column(String(64), nullable=False, comment='商品唯一 key')
    title = Column(String(128), nullable=False, comment='商品名称')
    desc = Column(Text, nullable=True, comment='商品描述（富文本 HTML）')
    price = Column(Numeric(10, 2), nullable=False, comment='价格（元）')
    expire_time = Column(Integer, nullable=True, comment='购买后有效时长（秒），NULL 表示永久')
    support_continue = Column(Boolean, nullable=False, default=False, comment='是否支持续费')
    icon = Column(String(512), nullable=True, comment='商品封面图 URL')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.utc_timestamp(),
                        onupdate=func.utc_timestamp(), comment='更新时间')
    deleted_at = Column(DateTime, nullable=True, comment='删除时间（软删除）')

    __table_args__ = (
        Index('uk_products_key', 'key', unique=True),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'title': self.title,
            'desc': self.desc or '',
            'price': float(self.price) if self.price is not None else 0.0,
            'expire_time': self.expire_time,
            'support_continue': bool(self.support_continue),
            'icon': self.icon or '',
            'created_at': to_iso_utc(self.created_at),
            'updated_at': to_iso_utc(self.updated_at),
        }


class Order(Base):
    """订单表"""
    __tablename__ = 'shop_orders'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    product_id = Column(BigInteger, nullable=False, comment='商品ID')
    product_key = Column(String(64), nullable=False, comment='商品 key（冗余）')
    out_trade_no = Column(String(64), nullable=False, comment='商户订单号（唯一）')
    trade_no = Column(String(64), nullable=True, comment='第三方平台交易号')
    status = Column(String(20), nullable=False, default='pending', comment='订单状态')
    amount = Column(Integer, nullable=False, comment='实付金额（分）')
    order_type = Column(String(16), nullable=False, default='purchase', comment='purchase/renew')
    expire_at = Column(DateTime, nullable=True, comment='权益到期时间')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.utc_timestamp(),
                        onupdate=func.utc_timestamp(), comment='更新时间')

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'

    __table_args__ = (
        Index('uk_orders_out_trade_no', 'out_trade_no', unique=True),
        Index('idx_orders_user_id', 'user_id'),
        Index('idx_orders_status', 'status'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'product_key': self.product_key,
            'out_trade_no': self.out_trade_no,
            'trade_no': self.trade_no or '',
            'status': self.status,
            'amount': int(self.amount) if self.amount is not None else 0,
            'order_type': self.order_type,
            'expire_at': to_iso_utc(self.expire_at),
            'created_at': to_iso_utc(self.created_at),
            'updated_at': to_iso_utc(self.updated_at),
        }
