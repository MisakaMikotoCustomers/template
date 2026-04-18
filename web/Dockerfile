FROM nginx:alpine

WORKDIR /app

# 整个 web 目录拷进去（后面会剔除非静态文件）
COPY . /app

# 1) nginx 配置 / 启动脚本 移出静态目录，避免被外部访问
# 2) 清理掉不应该对外暴露的文件
# 3) 接受 BUILD_VERSION 构建参数做缓存破坏
# 注：HTML 里静态资源引用形如 ?v=dev，构建时统一替换为真实版本号
RUN mv /app/nginx.conf /etc/nginx/conf.d/default.conf && \
    mv /app/entrypoint.sh /entrypoint.sh && \
    chmod +x /entrypoint.sh && \
    rm -f /app/Dockerfile /app/*.toml && \
    rm -rf /app/.git /app/.gitignore

ARG BUILD_VERSION=dev
ENV BUILD_VERSION=${BUILD_VERSION}

# 把 HTML 里的 ?v=xxx 替换为构建版本，保证静态资源缓存失效
RUN find /app -name '*.html' -exec sed -i "s/?v=[0-9A-Za-z_.-]*/?v=${BUILD_VERSION}/g" {} + && \
    echo "[build] applied BUILD_VERSION=${BUILD_VERSION}"

ENV APP_CONFIG_PATH=/config/config.toml

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
