#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一鉴权模块
- 普通用户路由：Bearer Token（存储于 DB）
- Admin 路由：静态 X-Admin-Token（来自配置文件）
- 支持 @skip_auth 跳过鉴权
"""

import logging

from flask import request, jsonify, current_app

from dao import user_dao

logger = logging.getLogger(__name__)


def skip_auth(f):
    """标记接口跳过全局鉴权"""
    setattr(f, '_skip_auth', True)
    return f


def _is_skip_auth_endpoint() -> bool:
    endpoint = request.endpoint
    if not endpoint:
        return False
    view_func = current_app.view_functions.get(endpoint)
    return bool(view_func and getattr(view_func, '_skip_auth', False))


def _do_auth_check():
    """执行鉴权逻辑"""
    config = current_app.config.get('APP_CONFIG')
    path = request.path

    # Admin 路由使用静态 Admin Token 鉴权
    if '/api/admin' in path:
        admin_token = request.headers.get('X-Admin-Token', '')
        if not admin_token or admin_token != (config.admin_token if config else ''):
            logger.warning("Admin auth failed: path=%s", path)
            return jsonify({'code': 401, 'message': '管理员认证失败'}), 401
        return None

    # 普通路由使用 Bearer Token 鉴权
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'code': 401, 'message': '缺少认证 Token'}), 401

    token = auth_header[7:]
    if not token:
        return jsonify({'code': 401, 'message': '缺少认证 Token'}), 401

    user_session = user_dao.get_session_by_token(token)
    if not user_session:
        return jsonify({'code': 401, 'message': 'Token 无效或已过期'}), 401

    user = user_dao.get_user_by_id(user_session.user_id)
    if not user:
        return jsonify({'code': 401, 'message': '用户不存在'}), 401

    request.current_user = user
    return None


def register_global_auth(app):
    """注册全局鉴权 before_request
    所有接口默认需要鉴权，仅 @skip_auth 标记的接口可跳过。
    """

    @app.before_request
    def _global_auth_guard():
        # CORS 预检请求放行
        if request.method == 'OPTIONS':
            return None
        # 标记了 @skip_auth 的接口放行
        if _is_skip_auth_endpoint():
            return None
        return _do_auth_check()
