#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""前端用户路由（注册 / 登录 / 当前用户 / 退出）"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from config_model import AppConfig
from routes.auth_plugin import skip_auth
from service.user_service import (
    UserServiceError,
    login_user,
    logout_user,
    register_user,
)

router = APIRouter()


class UserCredentials(BaseModel):
    name: str = ''
    password_hash: str = ''


def _app_config(request: Request) -> AppConfig:
    return request.app.state.app_config


def _ok(data=None, message: str = 'ok', code: int = 200) -> dict:
    return {'code': code, 'message': message, 'data': data}


def _err(message: str, code: int):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=code,
        content={'code': code, 'message': message, 'data': None},
    )


@router.post('/register')
@skip_auth
async def register(payload: UserCredentials, request: Request):
    """注册接口（无需登录）。

    注册黑名单 = 配置里 special_accounts 的 name 集合。
    """
    config = _app_config(request)
    reserved_names = [a.name for a in (config.auth.special_accounts or []) if a.name]
    try:
        info = await register_user(
            payload.name,
            payload.password_hash,
            session_expire_days=config.auth.session_expire_days,
            reserved_names=reserved_names,
        )
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok(info.to_dict(), message='注册成功', code=201)


@router.post('/login')
@skip_auth
async def login(payload: UserCredentials, request: Request):
    """登录接口（无需 token）。"""
    config = _app_config(request)
    try:
        info = await login_user(
            payload.name,
            payload.password_hash,
            session_expire_days=config.auth.session_expire_days,
        )
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok(info.to_dict(), message='登录成功')


@router.get('/me')
async def get_me(request: Request):
    """获取当前登录用户信息。"""
    return _ok(request.state.user.to_dict())


@router.post('/logout')
async def logout(request: Request):
    """退出登录：销毁当前 token。"""
    token = getattr(request.state, 'token', None)
    if token:
        await logout_user(token)
    return _ok(None, message='已退出登录')
