#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户 DAO - 纯数据库操作
"""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from .connection import get_session
from .models import User, UserSession


def get_user_by_username(username: str) -> Optional[User]:
    session = get_session()
    return session.query(User).filter(User.username == username).first()


def get_user_by_id(user_id: int) -> Optional[User]:
    session = get_session()
    return session.query(User).filter(User.id == user_id).first()


def create_user(username: str, password_hash: str) -> User:
    session = get_session()
    user = User(username=username, password_hash=password_hash)
    session.add(user)
    session.flush()
    return user


def create_session(user_id: int, expire_days: int = 30) -> UserSession:
    """创建用户 Token 会话"""
    session = get_session()
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expire_days)
    user_session = UserSession(user_id=user_id, token=token, expires_at=expires_at)
    session.add(user_session)
    session.flush()
    return user_session


def get_session_by_token(token: str) -> Optional[UserSession]:
    """校验 Token 是否有效（未过期）"""
    session = get_session()
    now = datetime.now(timezone.utc)
    return (session.query(UserSession)
            .filter(UserSession.token == token,
                    UserSession.expires_at > now)
            .first())
