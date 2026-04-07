# 多阶段构建：Node 打包前端 + Python 服务静态文件

# ── Stage 1: 构建前端 ────────────────────────────────────────────
FROM node:20-alpine AS builder

ARG BUILD_TAG=dev
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline

COPY . .

# 将 BUILD_TAG 传入 Vite 构建，注入到前端代码中
RUN VITE_BUILD_TAG=${BUILD_TAG} npm run build

# ── Stage 2: Flask 服务静态文件 ──────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config unset global.extra-index-url || true && \
    pip config set global.trusted-host mirrors.aliyun.com

RUN pip install --retries 10 flask
RUN pip install --retries 10 gunicorn
RUN pip install --retries 10 tomli

# 拷贝构建产物和 Python 服务文件
COPY --from=builder /app/dist /app/dist
COPY config_model.py main.py ./

CMD ["gunicorn", "--bind", "0.0.0.0:8081", "--workers", "2", "main:app"]
