#!/bin/sh
# 容器启动脚本：
#   1) 读取配置文件（APP_CONFIG_PATH，默认 /config/config.toml）
#      - [server].name          : 前端展示名
#      - [apiserver].host       : 后端主机（留空表示同域）
#      - [apiserver].path_prefix: 后端 API 前缀（默认 /api）
#   2) 生成 /app/config.json 供前端运行时读取
#   3) 启动 nginx（前台）
set -e

CONFIG_FILE="${APP_CONFIG_PATH:-/config/config.toml}"

# 提取指定 section 下某个 key 的字符串值（带去引号 / 去注释）
read_toml_str() {
    section="$1"
    key="$2"
    file="$3"
    awk -v section="[$section]" -v key="$key" '
        $0 == section { inside=1; next }
        /^\[/        { inside=0 }
        inside && $0 ~ ("^[[:space:]]*" key "[[:space:]]*=") {
            sub(/^[^=]*=[[:space:]]*/, "");
            sub(/[[:space:]]*(#.*)?$/, "");
            gsub(/^"|"$/, "");
            print; exit
        }' "$file"
}

APP_NAME="Template"
APISERVER_HOST=""
APISERVER_PATH_PREFIX="/api"

if [ -f "$CONFIG_FILE" ]; then
    NAME=$(read_toml_str server name "$CONFIG_FILE" || true)
    [ -n "$NAME" ] && APP_NAME="$NAME"

    HOST=$(read_toml_str apiserver host "$CONFIG_FILE" || true)
    APISERVER_HOST="$HOST"

    PREFIX=$(read_toml_str apiserver path_prefix "$CONFIG_FILE" || true)
    [ -n "$PREFIX" ] && APISERVER_PATH_PREFIX="$PREFIX"
    echo "[entrypoint] loaded config from $CONFIG_FILE"
else
    echo "[entrypoint] config file not found: $CONFIG_FILE, using defaults"
fi

# 生成前端运行时配置
cat > /app/config.json <<ENDJSON
{
  "server": {
    "name": "${APP_NAME}"
  },
  "apiserver": {
    "host": "${APISERVER_HOST}",
    "path_prefix": "${APISERVER_PATH_PREFIX}"
  }
}
ENDJSON

echo "[entrypoint] wrote /app/config.json server.name='${APP_NAME}' apiserver.host='${APISERVER_HOST}' apiserver.path_prefix='${APISERVER_PATH_PREFIX}'"

exec nginx -g 'daemon off;'
