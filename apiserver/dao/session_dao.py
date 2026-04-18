#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用户会话（token）异步 DAO"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from .connection import get_db_session
from .models import UserSession


def generate_session_token() -> str:
    """64 字符的随机 token"""
    return secrets.token_hex(32)


async def create_session(user_id: int, expire_days: int = 7) -> UserSession:
    """为指定用户创建 token 会话。"""
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expire_days)
    async with get_db_session() as session:
        user_session = UserSession(
            user_id=user_id, token=token, expires_at=expires_at
        )
        session.add(user_session)
        await session.flush()
        await session.refresh(user_session)
        return user_session


async def get_session_by_token(token: str) -> Optional[UserSession]:
    """按 token 获取未过期的会话。"""
    now = datetime.now(timezone.utc)
    async with get_db_session() as session:
        return await session.scalar(
            select(UserSession).where(
                UserSession.token == token,
                UserSession.expires_at > now,
            )
        )


async def delete_session(token: str) -> bool:
    """退出登录：物理删除 token 行。"""
    async with get_db_session() as session:
        user_session = await session.scalar(
            select(UserSession).where(UserSession.token == token)
        )
        if not user_session:
            return False
        await session.delete(user_session)
        return True
