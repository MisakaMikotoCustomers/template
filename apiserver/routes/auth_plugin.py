#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一鉴权 + traceId 中间件

三类路由各自的鉴权策略（/api 前缀下）：
  /api/admin/*  — Token 登录验证 → 必须是 admin 用户（账号名 == 'admin'）
  /api/app/*    — Token 登录验证 → 任意已登录用户
  /api/open/*   — X-Client-Secret 秘钥验证

除带有 @skip_auth 注解的接口外，所有接口都必须通过鉴权。

每次请求：
- 若 request header 携带 traceId 直接沿用，否则生成 auto-<uuid>
- 最终把 traceId 写进响应 header（供前端与链路追踪用）

请求上下文里会挂上：
- request.state.trace_id
- request.state.user : dao.models.User  （鉴权通过后）
"""

import logging
import uuid
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp

from dao import session_dao, user_dao
from dao.secret_dao import touch_secret_last_used
from service.user_service import get_user_by_secret

logger = logging.getLogger(__name__)


# ============================== 跳过注解 ==============================

def skip_auth(func):
    """标记路由函数无需鉴权（如登录/注册/健康检查）。"""
    setattr(func, '_skip_auth', True)
    return func


def _resolve_endpoint(request: Request):
    """BaseHTTPMiddleware 在路由匹配前执行，scope['endpoint'] 还未设置；
    需要自己遍历路由表找到匹配项，拿到 endpoint 原函数来检查注解。"""
    for route in request.app.router.routes:
        matches = getattr(route, 'matches', None)
        if matches is None:
            continue
        match, _ = matches(request.scope)
        if match == Match.FULL:
            return getattr(route, 'endpoint', None)
    return None


def _endpoint_skip_auth(request: Request) -> bool:
    endpoint = _resolve_endpoint(request)
    return bool(endpoint and getattr(endpoint, '_skip_auth', False))


# ============================== 工具 ==============================

def _json_error(code: int, message: str, trace_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={'code': code, 'message': message, 'data': None},
        headers={'traceId': trace_id},
    )


def _ensure_trace_id(request: Request) -> str:
    existing = getattr(request.state, 'trace_id', None)
    if existing:
        return existing
    trace_id = request.headers.get('traceId') or f"auto-{uuid.uuid4()}"
    request.state.trace_id = trace_id
    return trace_id


# ============================== Token 鉴权 ==============================

async def _authenticate_by_token(request: Request, trace_id: str) -> Optional[JSONResponse]:
    """Bearer Token 认证，成功则在 request.state.user 挂上 User。"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return _json_error(401, '缺少认证token', trace_id)
    if not auth_header.startswith('Bearer '):
        return _json_error(401, 'Token格式错误', trace_id)

    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return _json_error(401, '缺少认证token', trace_id)

    try:
        user_session = await session_dao.get_session_by_token(token)
        if not user_session:
            return _json_error(401, '无效的认证信息', trace_id)

        user = await user_dao.get_user_by_user_id(user_session.user_id)
        if not user:
            return _json_error(401, '无效的认证信息', trace_id)
    except Exception as e:
        logger.error('Token验证异常 traceId=%s err=%s', trace_id, e, exc_info=True)
        return _json_error(500, '认证服务异常', trace_id)

    request.state.user = user
    request.state.token = token

    try:
        await user_dao.update_last_access(user.user_id)
    except Exception as e:
        logger.warning('更新用户最近访问时间失败 traceId=%s err=%s', trace_id, e)
    return None


async def _authenticate_by_secret(request: Request, trace_id: str) -> Optional[JSONResponse]:
    """X-Client-Secret 秘钥认证。"""
    secret = request.headers.get('X-Client-Secret')
    if not secret:
        return _json_error(401, '缺少认证秘钥', trace_id)

    try:
        user = await get_user_by_secret(secret)
        if not user:
            return _json_error(401, '无效的秘钥', trace_id)
    except Exception as e:
        logger.error('秘钥验证异常 traceId=%s err=%s', trace_id, e, exc_info=True)
        return _json_error(500, '认证服务异常', trace_id)

    request.state.user = user

    try:
        await touch_secret_last_used(secret)
    except Exception as e:
        logger.warning('更新秘钥最近使用时间失败 traceId=%s err=%s', trace_id, e)
    return None


async def _auth_admin(request: Request, trace_id: str) -> Optional[JSONResponse]:
    err = await _authenticate_by_token(request, trace_id)
    if err:
        return err
    user = getattr(request.state, 'user', None)
    if not user or (user.name or '').lower() != 'admin':
        return _json_error(403, '需要管理员权限', trace_id)
    return None


async def _auth_app(request: Request, trace_id: str) -> Optional[JSONResponse]:
    return await _authenticate_by_token(request, trace_id)


async def _auth_open(request: Request, trace_id: str) -> Optional[JSONResponse]:
    return await _authenticate_by_secret(request, trace_id)


# ============================== 中间件 ==============================

class AuthMiddleware(BaseHTTPMiddleware):
    """全局鉴权 + traceId 注入中间件。

    说明：必须作为最外层（最后 add）的业务中间件，才能保证 traceId 总能注入响应。
    """

    def __init__(self, app: ASGIApp, api_prefix: str = '/api'):
        super().__init__(app)
        self.api_prefix = api_prefix.rstrip('/')
        self.admin_prefix = f'{self.api_prefix}/admin'
        self.app_prefix = f'{self.api_prefix}/app'
        self.open_prefix = f'{self.api_prefix}/open'

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        trace_id = _ensure_trace_id(request)

        if request.method == 'OPTIONS':
            response = await call_next(request)
            response.headers['traceId'] = trace_id
            return response

        # 非 /api 路径（静态资源、swagger 等）无需鉴权
        path = request.url.path
        needs_auth = path.startswith(self.api_prefix + '/') or path == self.api_prefix

        if needs_auth and not _endpoint_skip_auth(request):
            if path.startswith(self.admin_prefix):
                err = await _auth_admin(request, trace_id)
            elif path.startswith(self.app_prefix):
                err = await _auth_app(request, trace_id)
            elif path.startswith(self.open_prefix):
                err = await _auth_open(request, trace_id)
            else:
                logger.warning('访问未注册 API 路径 traceId=%s path=%s', trace_id, path)
                return _json_error(404, '接口不存在', trace_id)

            if err is not None:
                return err

        response = await call_next(request)
        response.headers['traceId'] = trace_id
        return response


def register_auth(app: FastAPI, api_prefix: str = '/api') -> None:
    """在 FastAPI 应用上挂载鉴权中间件。"""
    app.add_middleware(AuthMiddleware, api_prefix=api_prefix)
