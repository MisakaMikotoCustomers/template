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
import time
import traceback
import uuid
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
from dao.connection import get_engine
from dao.sql_interceptor import install_sql_interceptor
from routes.admin.admin import router as admin_router
from routes.app.feedback import router as app_feedback_router
from routes.app.secret import router as app_secret_router
from routes.app.user import router as app_user_router
from routes.auth_plugin import register_auth, skip_auth
from routes.open.ping import router as open_ping_router
from service.user_service import sync_special_accounts
from utils.log_utils import bind_context, init_logging, reset_context

# 注：init_logging 会重置 root handlers，下面的 basicConfig 仅在未启用
# 结构化日志时起作用（例如本地 dev 时 cls.enabled=False 也一样走 stdout JSON）。
# 真正的 logger 初始化放在 _load_config 之后，见模块末尾的 `init_logging(...)` 调用。
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
        # SQL 拦截器（可选）：必须在 init_database 之后、业务流量到达之前安装。
        if config.sql_interceptor.enabled:
            install_sql_interceptor(
                engine=get_engine(),
                slow_threshold_ms=config.sql_interceptor.slow_threshold_ms,
                max_sql_bytes=config.sql_interceptor.max_sql_bytes,
                log_params=config.sql_interceptor.log_params,
                max_params_bytes=config.sql_interceptor.max_params_bytes,
            )
        # 特殊账号 upsert：依赖 user 表已建好，必须在 init_database 之后
        await sync_special_accounts(config.auth.special_accounts)
        # APM Phase 2：SQLAlchemy 埋点需要真正的 engine，engine 在 init_database 里才建
        # 起来；FastAPI / httpx 不能放这里，详见 create_app 中的 Phase 1 注释。
        if getattr(config, 'apm', None) and config.apm.enabled:
            from utils.apm_utils import init_apm
            init_apm(apm_config=config.apm, engine=get_engine())
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

    # APM Phase 1：在 app 交给 uvicorn 之前挂 TracerProvider + FastAPIInstrumentor + HTTPX。
    # FastAPI/Starlette 的 middleware_stack 在 ASGI server 首次调用 app（含 lifespan
    # 协议）时 lazily 构建完成，之后 app.add_middleware(...) 无法进入已构建的栈——
    # 如果把 FastAPIInstrumentor 放到 lifespan 里挂，OpenTelemetryMiddleware 永远
    # 不会被调用，HTTP 请求不会生成 span，腾讯云 APM 控制台「接口分析」看不到数据。
    # 这里是 create_app 返回前的最后机会。enabled=false 时 init_apm 立即返回，零开销。
    if getattr(config, 'apm', None) and config.apm.enabled:
        from utils.apm_utils import init_apm
        init_apm(apm_config=config.apm, app=app)

    # CORS（开发期宽松，生产按需收紧）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['traceId'],
    )

    # 访问日志中间件：
    # - 入口绑定 trace_id / path / method 到 ContextVar，使整个请求内的所有
    #   `logger.info(...)` 自动带上这些字段；
    # - 出口读取 response.status / 已鉴权的 request.state.user，打一条
    #   `event=http.request` 汇总日志，并 reset ContextVar。
    # 注意 FastAPI 的 `app.middleware('http')` 是按注册反向入栈，auth 插件
    # 在后面 `register_auth(...)` 再注册，所以本中间件实际在最外层、
    # 会覆盖整个请求生命周期（含鉴权前的 401/403）。
    _http_logger = logging.getLogger('apiserver.http')

    @app.middleware('http')
    async def _access_log_middleware(request: Request, call_next):
        started = time.perf_counter()
        trace_id = request.headers.get('traceId') or f'auto-{uuid.uuid4()}'
        # 同步给 auth 插件，避免双生 trace_id（auth_plugin._ensure_trace_id
        # 读到 request.state.trace_id 就直接复用）。
        request.state.trace_id = trace_id
        token = bind_context(trace_id=trace_id, path=request.url.path, method=request.method)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = getattr(response, 'status_code', 500)
            return response
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            user = getattr(request.state, 'user', None)
            user_id = getattr(user, 'user_id', None) if user else None
            if user_id is not None:
                bind_context(user_id=user_id)
            _http_logger.info(
                'http.request %s %s status=%s duration_ms=%d',
                request.method, request.url.path, status_code, duration_ms,
                extra={
                    'event': 'http.request',
                    'status': status_code,
                    'latency_ms': duration_ms,
                },
            )
            reset_context(token)

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

    # 统一异常处理：所有 /api 下的异常都转换成 {code,message,data} 结构。
    # 为方便排查线上问题，500 系错误会把原始异常类型 + 消息 + traceback 放进
    # `data.debug`（结构化），前端可直接拿来展示，而不是面对一句"服务器内部错误"
    # 还得翻 docker logs。生产级部署若不希望把堆栈透出给终端用户，可把下方
    # `_build_debug_payload` 改为返回 None 或按 request 开关控制。
    def _build_debug_payload(exc: BaseException) -> dict:
        """把异常压成结构化 debug 载荷（类型、消息、完整 traceback）。"""
        tb_list = traceback.format_exception(type(exc), exc, exc.__traceback__)
        cause = exc.__cause__ or exc.__context__
        return {
            'type': f'{type(exc).__module__}.{type(exc).__name__}',
            'message': str(exc),
            'traceback': ''.join(tb_list),
            'cause': (
                f'{type(cause).__module__}.{type(cause).__name__}: {cause}'
                if cause is not None and cause is not exc else None
            ),
        }

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
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = '.'.join(str(x) for x in (first.get('loc') or []))
        detail_msg = first.get('msg') or '请求参数校验失败'
        message = f'请求参数校验失败：{loc} {detail_msg}' if loc else f'请求参数校验失败：{detail_msg}'
        return JSONResponse(
            status_code=400,
            content={
                'code': 400,
                'message': message,
                'data': {'errors': errors, 'debug': _build_debug_payload(exc)},
            },
            headers={'traceId': trace_id} if trace_id else None,
        )

    @app.exception_handler(Exception)
    async def _unhandled_exc_handler(request: Request, exc: Exception):
        logger.exception('Unhandled exception: %s', exc)
        trace_id = getattr(request.state, 'trace_id', '') or ''
        debug = _build_debug_payload(exc)
        # message 直接带上原始异常信息，前端不展开 debug 也能看到核心原因
        message = f'[{type(exc).__name__}] {str(exc) or "服务器内部错误"}'
        return JSONResponse(
            status_code=500,
            content={'code': 500, 'message': message, 'data': {'debug': debug}},
            headers={'traceId': trace_id} if trace_id else None,
        )

    return app


# ASGI 入口：`gunicorn main:app` / `uvicorn main:app`
_config = _load_config()
# 先初始化日志：`init_logging` 会清空 root handlers 并挂 stdout JSON，
# 若 cls.enabled=True 则额外挂 AsyncCLSHandler。必须在 create_app 之前，
# 否则 FastAPI/uvicorn 注册的默认 handler 会与之冲突。
init_logging(
    cls_config=_config.cls,
    service=_config.cls.service or 'apiserver',
    env=_config.cls.env or 'default',
    topic_id=_config.cls.topic_id,
)
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
