#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用户业务层：注册 / 登录 / 黑名单校验"""

from typing import List, Optional

from dao import session_dao, user_dao
from dao.models import User
from dao.secret_dao import get_user_id_by_secret


class UserServiceError(Exception):
    """业务错误（被 auth_plugin/路由层捕获并转成统一 JSON）。"""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code


class UserInfo:
    """对外返回的用户登录信息。"""

    def __init__(self, user_id: int, name: str, token: Optional[str] = None):
        self.user_id = user_id
        self.name = name
        self.token = token

    def to_dict(self) -> dict:
        data = {'user_id': self.user_id, 'name': self.name}
        if self.token is not None:
            data['token'] = self.token
        return data


def _normalize_blacklist(blacklist: List[str]) -> set:
    return {(name or '').strip().lower() for name in (blacklist or [])}


async def register_user(
    name: str,
    password_hash: str,
    *,
    session_expire_days: int,
    username_blacklist: List[str],
) -> UserInfo:
    """注册并直接返回带 token 的 UserInfo。

    校验：
    - 用户名/密码非空
    - 用户名 ≤ 32
    - 用户名不能在黑名单中（大小写不敏感）
    - 用户名必须唯一
    """
    name = (name or '').strip()
    password_hash = (password_hash or '').strip()

    if not name:
        raise UserServiceError('用户名不能为空')
    if not password_hash:
        raise UserServiceError('密码不能为空')
    if len(name) > 32:
        raise UserServiceError('用户名长度不能超过 32 个字符')

    blacklist = _normalize_blacklist(username_blacklist)
    if name.lower() in blacklist:
        raise UserServiceError('该用户名为系统保留账号，不允许注册', code=403)

    if await user_dao.check_user_name_exists(name):
        raise UserServiceError('用户名已存在', code=409)

    user = await user_dao.create_user(name, password_hash)
    session = await session_dao.create_session(user.user_id, expire_days=session_expire_days)
    return UserInfo(user.user_id, user.name, session.token)


async def login_user(
    name: str, password_hash: str, *, session_expire_days: int
) -> UserInfo:
    name = (name or '').strip()
    password_hash = (password_hash or '').strip()

    if not name or not password_hash:
        raise UserServiceError('用户名和密码不能为空')

    user = await user_dao.get_user_by_name(name)
    if not user or user.password_hash != password_hash:
        raise UserServiceError('用户名或密码错误', code=401)

    await user_dao.update_last_access(user.user_id)
    session = await session_dao.create_session(user.user_id, expire_days=session_expire_days)
    return UserInfo(user.user_id, user.name, session.token)


async def logout_user(token: str) -> None:
    await session_dao.delete_session(token)


async def get_user_by_secret(secret: str) -> Optional[User]:
    """open 接口使用：secret -> user。"""
    user_id = await get_user_id_by_secret(secret)
    if not user_id:
        return None
    return await user_dao.get_user_by_user_id(user_id)
