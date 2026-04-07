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


def _hash_password(password: str) -> str:
    """简单 SHA256 哈希（生产中建议使用 bcrypt）"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


@user_bp.route('/register', methods=['POST'])
@skip_auth
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空', 'data': None}), 400

    if len(username) > 64 or len(password) < 6:
        return jsonify({'code': 400, 'message': '用户名最长64字符，密码最少6字符', 'data': None}), 400

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
