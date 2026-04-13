#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
商品支付模板 - API Server
支持 Gunicorn + gevent 高并发部署
"""

import argparse
import logging
import os
import sys

# gevent monkey-patch 必须在所有其他 import 之前执行
# 仅在 Gunicorn/gevent worker 场景下生效；本地 flask 开发时无影响
try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    pass

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from config_model import AppConfig
from dao import init_database, remove_session
from routes.auth_plugin import register_global_auth, skip_auth
from routes.api.commercial import commercial_bp
from routes.admin.admin import admin_bp
from routes.api.user import user_bp


def create_app(config: AppConfig) -> Flask:
    """创建 Flask 应用"""
    app = Flask(__name__)
    app.json.ensure_ascii = False

    # 将配置存入 app.config，供路由层取用
    app.config['APP_CONFIG'] = config

    CORS(app, supports_credentials=True)

    prefix = config.server.url_prefix.rstrip('/') if config.server.url_prefix else ''

    app.register_blueprint(user_bp,       url_prefix=f'{prefix}/api/user')
    app.register_blueprint(commercial_bp, url_prefix=f'{prefix}/api/commercial')
    app.register_blueprint(admin_bp,      url_prefix=f'{prefix}/api/admin')
    register_global_auth(app)

    api_prefix = f'{prefix}/api'

    @app.errorhandler(Exception)
    def handle_exception(e):
        if not request.path.startswith(api_prefix):
            if isinstance(e, HTTPException):
                return e
            app.logger.exception('Unhandled non-API exception')
            return 'Internal Server Error', 500

        if isinstance(e, HTTPException):
            return jsonify({'code': e.code or 500, 'message': e.description or '请求处理失败', 'data': None}), e.code or 500

        app.logger.exception('Unhandled API exception')
        return jsonify({'code': 500, 'message': '服务器内部错误', 'data': None}), 500

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        remove_session()

    @app.route(f'{prefix}/api/health')
    @skip_auth
    def health():
        return {'code': 200, 'message': 'ok', 'data': {'status': 'healthy'}}

    return app


def _load_config(config_path: str) -> AppConfig:
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    return AppConfig.from_toml(config_path)


# Gunicorn 入口：gunicorn "main:app" 时读取环境变量 API_CONFIG 指定配置文件路径
_config_path = os.environ.get('API_CONFIG', 'config.toml')
if os.path.exists(_config_path):
    _config = AppConfig.from_toml(_config_path)
    init_database(_config.database)
    app = create_app(_config)
else:
    # 未找到配置文件时创建空 app，避免 import 报错；main() 会校验
    app = Flask(__name__)


def main():
    parser = argparse.ArgumentParser(description='Shop API Server')
    parser.add_argument('--config', '-c', type=str, default='config.toml',
                        help='Path to configuration file (TOML format)')
    args = parser.parse_args()

    config = _load_config(args.config)
    os.environ['API_CONFIG'] = args.config

    init_database(config.database)
    flask_app = create_app(config)

    print(f"Starting API Server on http://{config.server.host}:{config.server.port}")
    flask_app.run(host=config.server.host, port=config.server.port, debug=config.server.debug)


if __name__ == '__main__':
    main()
