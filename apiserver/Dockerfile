FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    APP_CONFIG_PATH=/config/config.toml

# 使用阿里云 PyPI 镜像，加速国内构建
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config unset global.extra-index-url || true && \
    pip config set global.trusted-host mirrors.aliyun.com

# 每个依赖单独一层，保证缓存粒度
RUN pip install --retries 10 "fastapi>=0.110"
RUN pip install --retries 10 "uvicorn[standard]>=0.27"
RUN pip install --retries 10 "uvloop>=0.19; sys_platform != 'win32'"
RUN pip install --retries 10 "httptools>=0.6"
RUN pip install --retries 10 "gunicorn>=21.2"
RUN pip install --retries 10 "sqlalchemy[asyncio]>=2.0"
RUN pip install --retries 10 "aiomysql>=0.2.0"
RUN pip install --retries 10 "httpx>=0.27"
RUN pip install --retries 10 "pydantic>=2.5"
RUN pip install --retries 10 "tomli>=2.0; python_version < '3.11'"
# 腾讯云 CLS 日志上报 SDK（注意：不是 tencentcloud-sdk-python-cls，那是管理 API）
# cls.enabled=false 时不会 import；为避免 ai-task 注入 [log] 段后重启报错先装上。
#
# tencentcloud-cls-sdk-python 固定依赖 lz4<=3.1.2 / python-snappy<=0.7.0，
# 这些老版本在 python:3.11-slim 上没有 wheel，会触发源码编译而 slim 镜像没 gcc
# （实测报错：RUN pip install tencentcloud-cls-sdk-python → lz4 编译 gcc: not found）。
# 方案：先装兼容的新版 lz4（API 不变），然后 --no-deps 跳过过期 pin。
# python-snappy 只在消费端用，上报路径不需要，故不安装。
# --no-deps 不会装 SDK 自带的 requests，logclient 导入会失败（ModuleNotFoundError: requests）。
RUN pip install --retries 10 "six" "protobuf>=3.20,<4" "python-dateutil" "lz4" "requests"
RUN pip install --retries 10 --no-deps "tencentcloud-cls-sdk-python"

COPY . /app

EXPOSE 8080

# 以 gunicorn + uvicorn worker 启动，充分利用 uvloop 事件循环
# 进程数由配置 server.workers 指定；此处默认 1（适合 I/O 密集型）
CMD ["gunicorn", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "1", \
     "-b", "0.0.0.0:8080", \
     "--worker-connections", "2048", \
     "--timeout", "120", \
     "main:app"]
