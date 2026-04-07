#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
商品支付模板 - Web 前端服务
使用 Flask 服务 Vite 构建后的静态文件（dist/）
"""

import argparse
import logging
import os
import sys

from flask import Flask, send_from_directory, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from config_model import WebConfig


def create_app(config: WebConfig) -> Flask:
    """创建 Flask 应用，服务 dist/ 目录下的静态文件"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_folder = os.path.join(base_dir, 'dist')

    app = Flask(__name__, static_folder=static_folder, static_url_path='')

    url_prefix = config.server.url_prefix.rstrip('/') if config.server.url_prefix else ''

    @app.route(f'{url_prefix}/config.json')
    def get_config():
        """前端通过此接口获取后端地址"""
        return jsonify({
            'apiserver': {
                'host': config.apiserver.host,
                'path_prefix': config.apiserver.path_prefix,
            },
        })

    @app.route(f'{url_prefix}/', defaults={'path': ''})
    @app.route(f'{url_prefix}/<path:path>')
    def serve(path):
        if path and os.path.exists(os.path.join(static_folder, path)):
            return send_from_directory(static_folder, path)
        return send_from_directory(static_folder, 'index.html')

    return app


def _load_config() -> WebConfig:
    config_path = os.environ.get('WEB_CONFIG', 'config.toml')
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    return WebConfig.from_toml(config_path)


# Gunicorn 入口
app = create_app(_load_config())


def main():
    parser = argparse.ArgumentParser(description='Shop Web Server')
    parser.add_argument('--config', '-c', type=str, default=None)
    args = parser.parse_args()

    if args.config:
        os.environ['WEB_CONFIG'] = args.config

    config = _load_config()
    flask_app = create_app(config)

    print(f"Starting Web Server on http://{config.server.host}:{config.server.port}")
    flask_app.run(host=config.server.host, port=config.server.port, debug=False)


if __name__ == '__main__':
    main()
