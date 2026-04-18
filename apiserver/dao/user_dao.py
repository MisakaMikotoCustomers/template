#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户数据访问对象（异步）

- 8 位 user_id 随机生成：10000000 ~ 99999999（首位 1-9）
- 所有跨表关联使用 user_id
"""

import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from .connection import get_db_session
from .models import User


def _random_public_user_id() -> int:
    """8 位随机整数，首位 1-9。"""
    return random.randint(10_000_000, 99_999_999)


async def _allocate_unique_user_id(session) -> int:
    """在事务内尝试分配一个不冲突的 8 位 user_id。"""
    for _ in range(500):
        uid = _random_public_user_id()
        exists = await session.scalar(
            select(User.id).where(User.user_id == uid).limit(1)
        )
        if not exists:
            return uid
    raise RuntimeError('无法生成唯一的 8 位 user_id，请稍后重试')


async def create_user(name: str, password_hash: str) -> User:
    """创建用户并自动分配 user_id。"""
    async with get_db_session() as session:
        uid = await _allocate_unique_user_id(session)
        user = User(name=name, password_hash=password_hash, user_id=uid)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def get_user_by_name(name: str) -> Optional[User]:
    async with get_db_session() as session:
        return await session.scalar(select(User).where(User.name == name))


async def get_user_by_user_id(user_id: int) -> Optional[User]:
    """通过对外 user_id 获取用户。"""
    async with get_db_session() as session:
        return await session.scalar(select(User).where(User.user_id == user_id))


async def check_user_name_exists(name: str) -> bool:
    async with get_db_session() as session:
        row = await session.scalar(select(User.id).where(User.name == name).limit(1))
        return row is not None


async def update_last_access(user_id: int) -> None:
    async with get_db_session() as session:
        await session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(last_access_at=datetime.now(timezone.utc))
        )


async def upsert_user_by_name(name: str, password_hash: str) -> User:
    """按 name upsert 用户：存在则刷新 password_hash，不存在则创建并分配 user_id。

    用于 special_accounts 启动时对齐 user 表；name 唯一索引是 DDL 约束，
    并发插入冲突时由上层重试或容忍失败（启动期场景单进程即可）。
    """
    async with get_db_session() as session:
        existing = await session.scalar(select(User).where(User.name == name))
        if existing:
            await session.execute(
                update(User)
                .where(User.id == existing.id)
                .values(password_hash=password_hash)
            )
            await session.flush()
            return existing
        uid = await _allocate_unique_user_id(session)
        user = User(name=name, password_hash=password_hash, user_id=uid)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user
