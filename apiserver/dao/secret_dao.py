#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用户秘钥（open 接口鉴权）异步 DAO"""

import secrets as secrets_module
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update

from .connection import get_db_session
from .models import UserSecret


async def list_user_secrets(user_id: int) -> List[UserSecret]:
    """获取用户所有未删除的秘钥。"""
    async with get_db_session() as session:
        result = await session.execute(
            select(UserSecret)
            .where(UserSecret.user_id == user_id, UserSecret.deleted_at.is_(None))
            .order_by(UserSecret.created_at.asc())
        )
        return list(result.scalars().all())


async def create_user_secret(user_id: int, name: str) -> UserSecret:
    """生成一条 64 位随机秘钥。"""
    async with get_db_session() as session:
        secret_row = UserSecret(
            user_id=user_id,
            name=name,
            secret=secrets_module.token_hex(32),
        )
        session.add(secret_row)
        await session.flush()
        await session.refresh(secret_row)
        return secret_row


async def delete_user_secret(secret_id: int, user_id: int) -> bool:
    async with get_db_session() as session:
        result = await session.execute(
            update(UserSecret)
            .where(
                UserSecret.id == secret_id,
                UserSecret.user_id == user_id,
                UserSecret.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0


async def get_user_id_by_secret(secret: str) -> Optional[int]:
    """通过 secret 查 user_id（仅限有效秘钥）。"""
    async with get_db_session() as session:
        return await session.scalar(
            select(UserSecret.user_id).where(
                UserSecret.secret == secret,
                UserSecret.deleted_at.is_(None),
            )
        )


async def touch_secret_last_used(secret: str) -> None:
    async with get_db_session() as session:
        await session.execute(
            update(UserSecret)
            .where(UserSecret.secret == secret, UserSecret.deleted_at.is_(None))
            .values(last_used_at=datetime.now(timezone.utc))
        )
