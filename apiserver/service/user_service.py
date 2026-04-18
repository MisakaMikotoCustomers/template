#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用户业务层：注册 / 登录 / 保留账号校验 / special_accounts 启动同步"""

import hashlib
import logging
from typing import Iterable, List, Optional

from dao import session_dao, user_dao
from dao.models import User
from dao.secret_dao import get_user_id_by_secret

logger = logging.getLogger(__name__)


def _hash_password_like_frontend(plain: str) -> str:
    """与前端 web/js/utils.js 中 hashPassword 保持一致：SHA-256 hex。

    前端登录/注册都是把明文做一次 SHA-256 再传给后端，user.password_hash
    存的就是这个 hex；special_accounts 里填的是明文密码，启动同步时按同一
    算法落库，这样管理员用前端正常登录即可匹配。
    """
    return hashlib.sha256((plain or '').encode('utf-8')).hexdigest()


async def sync_special_accounts(accounts: Iterable) -> None:
    """启动期对齐特殊账号到 user 表。

    - name 去空白；空 name 跳过并打 warning
    - password 允许明文空串吗？——不允许，空密码无法登录，跳过并打 warning
    - 存在同名 user → 更新 password_hash
    - 不存在 → 新建（自动分配 user_id）
    - 单条失败不阻塞整体（只记日志），启动阶段尽量不让一个 typo 拖垮服务
    """
    for acc in accounts or []:
        name = (getattr(acc, 'name', '') or '').strip()
        password = getattr(acc, 'password', '') or ''
        if not name:
            logger.warning('special_accounts: skip entry with empty name')
            continue
        if not password:
            logger.warning('special_accounts: skip %s due to empty password', name)
            continue
        try:
            pwd_hash = _hash_password_like_frontend(password)
            await user_dao.upsert_user_by_name(name=name, password_hash=pwd_hash)
            logger.info('special_accounts: upserted name=%s', name)
        except Exception as e:
            logger.exception('special_accounts: upsert failed name=%s: %s', name, e)


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


def _normalize_names(names: List[str]) -> set:
    return {(name or '').strip().lower() for name in (names or [])}


async def register_user(
    name: str,
    password_hash: str,
    *,
    session_expire_days: int,
    reserved_names: List[str],
) -> UserInfo:
    """注册并直接返回带 token 的 UserInfo。

    校验：
    - 用户名/密码非空
    - 用户名 ≤ 32
    - 用户名不能命中保留名单（大小写不敏感，完全匹配；即 special_accounts 里的 name）
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

    reserved = _normalize_names(reserved_names)
    if name.lower() in reserved:
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
