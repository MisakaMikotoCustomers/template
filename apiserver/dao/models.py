#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM 模型定义

- 用户表：user_id 是 8 位随机整数（首位 1-9），所有跨表关联都用 user_id
- 反馈表：feedback_key 是 8 位随机字符串（大小写字母+数字），(user_id, feedback_key) 唯一
"""

from datetime import datetime, timezone
from typing import Optional  # noqa: F401 (used in type hints inside method signatures)

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 基类"""
    pass


def to_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """统一将 datetime 序列化为 UTC ISO8601 字符串。"""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class User(Base):
    """用户表"""
    __tablename__ = 'tpl_users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, nullable=False, unique=True,
        comment='对外用户编号（8位随机整数，首位非0），所有跨表关联都用此列'
    )
    name = Column(String(64), nullable=False, comment='用户名（唯一）')
    password_hash = Column(String(256), nullable=False, comment='密码哈希')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')
    updated_at = Column(
        DateTime, server_default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(), comment='更新时间'
    )
    last_access_at = Column(DateTime, nullable=True, comment='最后访问时间')

    __table_args__ = (
        Index('uk_tpl_users_name', 'name', unique=True),
        Index('uk_tpl_users_user_id', 'user_id', unique=True),
    )

    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'name': self.name,
            'created_at': to_iso_utc(self.created_at),
            'last_access_at': to_iso_utc(self.last_access_at),
        }


class UserSession(Base):
    """用户会话（token）表"""
    __tablename__ = 'tpl_user_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment='对外 user_id')
    token = Column(String(128), nullable=False, comment='Bearer token')
    expires_at = Column(DateTime, nullable=False, comment='过期时间（UTC）')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')

    __table_args__ = (
        Index('uk_tpl_sessions_token', 'token', unique=True),
        Index('idx_tpl_sessions_user_id', 'user_id'),
    )


class UserSecret(Base):
    """用户秘钥表（open 接口鉴权用）"""
    __tablename__ = 'tpl_user_secrets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment='对外 user_id')
    name = Column(String(64), nullable=False, comment='秘钥名称/用途')
    secret = Column(String(128), nullable=False, comment='随机秘钥')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')
    last_used_at = Column(DateTime, nullable=True, comment='最近使用时间')
    deleted_at = Column(DateTime, nullable=True, comment='软删除时间，不为空即已删除')

    __table_args__ = (
        Index('uk_tpl_secrets_secret', 'secret', unique=True),
        Index('idx_tpl_secrets_user_id', 'user_id'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'secret': self.secret,
            'created_at': to_iso_utc(self.created_at),
            'last_used_at': to_iso_utc(self.last_used_at),
        }


class Feedback(Base):
    """用户反馈（会话）表

    一个反馈 = 一条会话，包含多条用户/管理员沟通记录（见 FeedbackMessage）。
    (user_id, feedback_key) 唯一；admin 通过这两个字段定位任意用户的反馈会话。
    """
    __tablename__ = 'tpl_feedbacks'

    STATUS_OPEN = 'open'                # 待处理（新建默认）
    STATUS_PROCESSING = 'processing'    # 处理中
    STATUS_RESOLVED = 'resolved'        # 已解决
    STATUS_CLOSED = 'closed'            # 已关闭
    ALLOWED_STATUS = (STATUS_OPEN, STATUS_PROCESSING, STATUS_RESOLVED, STATUS_CLOSED)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment='提交者的对外 user_id')
    feedback_key = Column(
        String(8), nullable=False,
        comment='8 位随机字符串（大小写字母+数字），(user_id, feedback_key) 唯一'
    )
    title = Column(String(128), nullable=True, comment='会话标题（由首条消息摘要自动生成）')
    status = Column(
        String(16), nullable=False, default=STATUS_OPEN,
        server_default=STATUS_OPEN, comment='会话状态 open/processing/resolved/closed'
    )
    last_message_at = Column(DateTime, nullable=True, comment='最近一条消息时间')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')
    updated_at = Column(
        DateTime, server_default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(), comment='更新时间'
    )

    __table_args__ = (
        Index('uk_tpl_feedback_user_key', 'user_id', 'feedback_key', unique=True),
        Index('idx_tpl_feedback_user_id', 'user_id'),
        Index('idx_tpl_feedback_status', 'status'),
    )

    def to_dict(self, last_message: Optional[str] = None) -> dict:
        return {
            'feedback_key': self.feedback_key,
            'user_id': self.user_id,
            'title': self.title,
            'status': self.status,
            'last_message': last_message,
            'last_message_at': to_iso_utc(self.last_message_at),
            'created_at': to_iso_utc(self.created_at),
            'updated_at': to_iso_utc(self.updated_at),
        }


class FeedbackMessage(Base):
    """反馈会话中的一条消息（用户或管理员发送）"""
    __tablename__ = 'tpl_feedback_messages'

    SENDER_USER = 'user'
    SENDER_ADMIN = 'admin'
    ALLOWED_SENDER = (SENDER_USER, SENDER_ADMIN)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, nullable=False,
        comment='会话所属用户的 user_id（反馈归属用户，非发送者）'
    )
    feedback_key = Column(String(8), nullable=False, comment='所属反馈会话 key')
    sender_type = Column(String(16), nullable=False, comment='user / admin')
    sender_name = Column(String(64), nullable=True, comment='发送者用户名快照（展示用）')
    content = Column(Text, nullable=False, comment='消息正文')
    created_at = Column(DateTime, server_default=func.utc_timestamp(), comment='创建时间')

    __table_args__ = (
        Index('idx_tpl_fb_msg_session', 'user_id', 'feedback_key', 'id'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'sender_type': self.sender_type,
            'sender_name': self.sender_name,
            'content': self.content,
            'created_at': to_iso_utc(self.created_at),
        }
