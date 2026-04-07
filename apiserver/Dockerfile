FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

# Configure pip mirror: Aliyun PyPI mirror
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config unset global.extra-index-url || true && \
    pip config set global.trusted-host mirrors.aliyun.com

# Install runtime dependencies
RUN pip install --retries 10 "flask>=2.0.0"
RUN pip install --retries 10 "flask-cors>=4.0.0"
RUN pip install --retries 10 "werkzeug>=2.0.0"
RUN pip install --retries 10 "pymysql>=1.0.0"
RUN pip install --retries 10 "sqlalchemy>=2.0.0"
RUN pip install --retries 10 "tomli>=2.0.0"
RUN pip install --retries 10 "gunicorn>=21.0.0"
RUN pip install --retries 10 "gevent>=23.0.0"
RUN pip install --retries 10 "cryptography>=41.0.0"
RUN pip install --retries 10 "cos-python-sdk-v5>=1.9.0"

COPY . /app

# 生产环境使用 Gunicorn + gevent worker 启动
# workers = 2*CPU+1，每个 worker 使用 gevent 协程，支持高并发
CMD ["gunicorn", \
     "--worker-class", "gevent", \
     "--workers", "4", \
     "--worker-connections", "1000", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "60", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "main:app"]
