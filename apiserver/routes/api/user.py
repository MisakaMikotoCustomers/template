#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户路由：注册、登录
"""

import hashlib
import logging

from flask import Blueprint, request, jsonify

from dao import get_db_session
from dao import user_dao
from routes.auth_plugin import skip_auth

logger = logging.getLogger(__name__)
user_bp = Blueprint('user', __name__)


_HEX_CHARS = frozenset('0123456789abcdef')
# 保留用户名，不允许注册
_RESERVED_USERNAMES = frozenset({'admin'})


def _is_client_hash(value: str) -> bool:
    """校验是否为合法的 SHA256 十六进制字符串（64 位）"""
    return len(value) == 64 and all(c in _HEX_CHARS for c in value.lower())


def _hash_password(client_hash: str) -> str:
    """对前端已哈希的密码再做一次 SHA256，存入 DB（双重哈希）"""
    return hashlib.sha256(client_hash.encode('utf-8')).hexdigest()


@user_bp.route('/register', methods=['POST'])
@skip_auth
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    normalized_username = username.lower()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空', 'data': None}), 400

    if len(username) > 64:
        return jsonify({'code': 400, 'message': '用户名最长64字符', 'data': None}), 400
    if normalized_username in _RESERVED_USERNAMES:
        return jsonify({'code': 403, 'message': '该用户名为系统保留账号，不允许注册', 'data': None}), 403

    # 前端负责在 hash 前做最小长度校验，后端只验证格式
    if not _is_client_hash(password):
        return jsonify({'code': 400, 'message': 'password 格式错误（需为前端 SHA256 哈希值）', 'data': None}), 400

    with get_db_session():
        existing = user_dao.get_user_by_username(username)
        if existing:
            return jsonify({'code': 409, 'message': '用户名已存在', 'data': None}), 409

        password_hash = _hash_password(password)
        user = user_dao.create_user(username, password_hash)
        session = user_dao.create_session(user.id)

    return jsonify({'code': 200, 'message': 'ok', 'data': {
        'token': session.token,
        'user': user.to_dict(),
    }})


@user_bp.route('/login', methods=['POST'])
@skip_auth
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空', 'data': None}), 400

    if not _is_client_hash(password):
        return jsonify({'code': 400, 'message': 'password 格式错误（需为前端 SHA256 哈希值）', 'data': None}), 400

    user = user_dao.get_user_by_username(username)
    if not user or user.password_hash != _hash_password(password):
        return jsonify({'code': 401, 'message': '用户名或密码错误', 'data': None}), 401

    with get_db_session():
        session = user_dao.create_session(user.id)

    return jsonify({'code': 200, 'message': 'ok', 'data': {
        'token': session.token,
        'user': user.to_dict(),
    }})


@user_bp.route('/me', methods=['GET'])
def me():
    user = request.current_user
    return jsonify({'code': 200, 'message': 'ok', 'data': user.to_dict()})
