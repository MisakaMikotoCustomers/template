# 多阶段构建：Node 打包前端 + Python 服务静态文件

# ── Stage 1: 构建前端 ────────────────────────────────────────────
FROM node:20-alpine AS builder

ARG BUILD_TAG=dev
WORKDIR /app

# 走国内 npm 镜像，和下面 pip aliyun 镜像保持一致，避免跨境拉包慢/失败
RUN npm config set registry https://registry.npmmirror.com

COPY package.json package-lock.json* ./
# 有 lock 文件走 ci（确定性安装，速度快）；没有则回退 install 并生成 lock。
# 模板项目不强制提交 package-lock.json，用户 clone 后即可直接构建。
RUN if [ -f package-lock.json ]; then \
        npm ci --prefer-offline; \
    else \
        npm install --prefer-offline --no-audit --no-fund; \
    fi

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
