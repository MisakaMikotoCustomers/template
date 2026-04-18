#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Template API Server —— FastAPI + async I/O

架构（对应技术选型图）：
  Web 框架    : FastAPI（原生 async/await）
  ASGI 服务器 : uvicorn + uvloop（I/O 密集型下极高吞吐）
  进程管理    : gunicorn（--worker-class uvicorn.workers.UvicornWorker）
  数据库      : SQLAlchemy 2.0 async + aiomysql
  HTTP 客户端 : httpx.AsyncClient（连接池复用；业务可按需引入）

启动入口：
  - `python main.py` —— 本地开发：启动 uvicorn 单进程
  - `gunicorn main:app -k uvicorn.workers.UvicornWorker -w N` —— 生产部署
  - 配置文件路径取环境变量 APP_CONFIG_PATH，默认 /config/config.toml
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# uvloop 在非 Windows 环境下启用，显著提升事件循环吞吐
try:
    if sys.platform != 'win32':
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from config_model import AppConfig
from dao import dispose_engine, init_database
from routes.admin.admin import router as admin_router
from routes.app.feedback import router as app_feedback_router
from routes.app.secret import router as app_secret_router
from routes.app.user import router as app_user_router
from routes.auth_plugin import register_auth, skip_auth
from routes.open.ping import router as open_ping_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('apiserver')


def _load_config() -> AppConfig:
    try:
        return AppConfig.load()
    except FileNotFoundError as e:
        print(f"[fatal] {e}")
        sys.exit(1)


def create_app(config: AppConfig) -> FastAPI:
    prefix = (config.server.url_prefix or '').rstrip('/')
    api_prefix = f'{prefix}/api'

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_database(config.database)
        logger.info(
            'Database initialized: %s:%s/%s',
            config.database.url, config.database.port, config.database.database,
        )
        yield
        await dispose_engine()
        logger.info('Database engine disposed')

    app = FastAPI(
        title='Template API Server',
        version='1.0.0',
        lifespan=lifespan,
        docs_url=f'{prefix}/docs',
        openapi_url=f'{prefix}/openapi.json',
        redoc_url=None,
    )
    app.state.app_config = config

    # CORS（开发期宽松，生产按需收紧）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['traceId'],
    )

    # 路由：/api/app/*
    app.include_router(app_user_router, prefix=f'{api_prefix}/app/user', tags=['app-user'])
    app.include_router(app_feedback_router, prefix=f'{api_prefix}/app/feedback', tags=['app-feedback'])
    app.include_router(app_secret_router, prefix=f'{api_prefix}/app/secret', tags=['app-secret'])

    # 路由：/api/admin/*
    app.include_router(admin_router, prefix=f'{api_prefix}/admin', tags=['admin'])

    # 路由：/api/open/*
    app.include_router(open_ping_router, prefix=f'{api_prefix}/open', tags=['open'])

    # 健康检查（无需鉴权）
    @app.get(f'{api_prefix}/health')
    @skip_auth
    async def health():
        return {'code': 200, 'message': 'ok', 'data': {'status': 'healthy'}}

    # 鉴权中间件必须最后注册（最外层）：这样它能拦到其他中间件之后的请求并注入 traceId
    register_auth(app, api_prefix=api_prefix)

    # 统一异常处理：所有 /api 下的异常都转换成 {code,message,data} 结构
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(request: Request, exc: StarletteHTTPException):
        trace_id = getattr(request.state, 'trace_id', '') or ''
        return JSONResponse(
            status_code=exc.status_code,
            content={'code': exc.status_code, 'message': exc.detail or '请求失败', 'data': None},
            headers={'traceId': trace_id} if trace_id else None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, 'trace_id', '') or ''
        return JSONResponse(
            status_code=400,
            content={'code': 400, 'message': '请求参数校验失败', 'data': exc.errors()},
            headers={'traceId': trace_id} if trace_id else None,
        )

    @app.exception_handler(Exception)
    async def _unhandled_exc_handler(request: Request, exc: Exception):
        logger.exception('Unhandled exception: %s', exc)
        trace_id = getattr(request.state, 'trace_id', '') or ''
        return JSONResponse(
            status_code=500,
            content={'code': 500, 'message': '服务器内部错误', 'data': None},
            headers={'traceId': trace_id} if trace_id else None,
        )

    return app


# ASGI 入口：`gunicorn main:app` / `uvicorn main:app`
_config = _load_config()
app = create_app(_config)


def main() -> None:
    """本地开发直接运行：`python main.py`"""
    import uvicorn
    config = app.state.app_config
    uvicorn.run(
        'main:app',
        host=config.server.host,
        port=config.server.port,
        workers=config.server.workers,
        log_level=config.server.log_level,
        loop='uvloop' if sys.platform != 'win32' else 'asyncio',
    )


if __name__ == '__main__':
    main()
