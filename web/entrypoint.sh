#!/bin/sh
# 容器启动脚本：
#   1) 读取配置文件（APP_CONFIG_PATH，默认 /config/config.toml）
#      - [server].name          : 前端展示名
#      - [apiserver].host       : 后端主机（留空表示同域）
#      - [apiserver].path_prefix: 后端 API 前缀（默认 /api）
#      - [rum].*                : 腾讯云 RUM（Aegis）前端监控配置
#          enabled, id, uin, spa, report_api_speed,
#          report_asset_speed, env, version, sample_rate, src
#        · [rum].version 留空时，退化使用环境变量 BUILD_VERSION
#          （由构建镜像时写入，一般是 8 位 git commit），
#          方便 RUM 后台按版本区分异常。
#   2) 生成 /app/config.json 供前端运行时读取
#   3) 启动 nginx（前台）
set -e

CONFIG_FILE="${APP_CONFIG_PATH:-/config/config.toml}"
BUILD_VERSION="${BUILD_VERSION:-}"

# 提取指定 section 下某个 key 的字符串值（带去引号 / 去注释），
# 供传统的“字符串类”字段使用（如 server.name、apiserver.host）。
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

# 提取 key = value 等号右侧的原始字面量（保留引号 / 布尔 / 数字），
# 用于直接嵌入 JSON。key 不存在时返回空字符串。
# 这样 true/false/数字不会被错误地转成字符串，
# 而字符串值（带引号）也会被原样保留。
get_toml_raw() {
    section="$1"
    key="$2"
    file="$3"
    awk -v sec="$section" -v k="$key" '
        $0 ~ "^\\["sec"\\]" { in_section = 1; next }
        /^\[/ { in_section = 0 }
        in_section && $0 ~ "^[[:space:]]*"k"[[:space:]]*=" {
            sub(/^[^=]*=[[:space:]]*/, "")
            sub(/[[:space:]]*(#.*)?$/, "")
            print
            exit
        }
    ' "$file"
}

# 如果 $1 非空就输出 $1，否则输出 JSON 默认值 $2。
raw_or_default() {
    if [ -z "$1" ]; then
        printf '%s' "$2"
    else
        printf '%s' "$1"
    fi
}

# 去掉前后一对双引号（若存在）。
strip_quotes() {
    printf '%s' "$1" | sed 's/^"//; s/"$//'
}

APP_NAME="Template"
APISERVER_HOST=""
APISERVER_PATH_PREFIX="/api"

# ---------- rum 默认（关闭，全部字段占位） ----------
RUM_ENABLED="false"
RUM_ID='""'
RUM_UIN='""'
RUM_SPA="true"
RUM_REPORT_API_SPEED="true"
RUM_REPORT_ASSET_SPEED="true"
RUM_ENV='""'
RUM_VERSION='""'
RUM_SAMPLE_RATE="1.0"
RUM_SRC='"https://tam.cdn-go.cn/aegis-sdk/latest/aegis.min.js"'

if [ -f "$CONFIG_FILE" ]; then
    NAME=$(read_toml_str server name "$CONFIG_FILE" || true)
    [ -n "$NAME" ] && APP_NAME="$NAME"

    HOST=$(read_toml_str apiserver host "$CONFIG_FILE" || true)
    APISERVER_HOST="$HOST"

    PREFIX=$(read_toml_str apiserver path_prefix "$CONFIG_FILE" || true)
    [ -n "$PREFIX" ] && APISERVER_PATH_PREFIX="$PREFIX"

    # ---------- rum（原始字面量，用于 JSON 直出） ----------
    RUM_ENABLED=$(raw_or_default "$(get_toml_raw rum enabled "$CONFIG_FILE")" "$RUM_ENABLED")
    RUM_ID=$(raw_or_default "$(get_toml_raw rum id "$CONFIG_FILE")" "$RUM_ID")
    RUM_UIN=$(raw_or_default "$(get_toml_raw rum uin "$CONFIG_FILE")" "$RUM_UIN")
    RUM_SPA=$(raw_or_default "$(get_toml_raw rum spa "$CONFIG_FILE")" "$RUM_SPA")
    RUM_REPORT_API_SPEED=$(raw_or_default "$(get_toml_raw rum report_api_speed "$CONFIG_FILE")" "$RUM_REPORT_API_SPEED")
    RUM_REPORT_ASSET_SPEED=$(raw_or_default "$(get_toml_raw rum report_asset_speed "$CONFIG_FILE")" "$RUM_REPORT_ASSET_SPEED")
    RUM_ENV=$(raw_or_default "$(get_toml_raw rum env "$CONFIG_FILE")" "$RUM_ENV")
    RUM_SAMPLE_RATE=$(raw_or_default "$(get_toml_raw rum sample_rate "$CONFIG_FILE")" "$RUM_SAMPLE_RATE")
    RUM_SRC=$(raw_or_default "$(get_toml_raw rum src "$CONFIG_FILE")" "$RUM_SRC")

    # version: 优先使用 toml 中显式值；为空则退化到 BUILD_VERSION。
    RUM_VERSION_RAW=$(get_toml_raw rum version "$CONFIG_FILE")
    RUM_VERSION_STR=$(strip_quotes "$RUM_VERSION_RAW")
    if [ -z "$RUM_VERSION_STR" ] && [ -n "$BUILD_VERSION" ]; then
        RUM_VERSION='"'"$BUILD_VERSION"'"'
    else
        RUM_VERSION=$(raw_or_default "$RUM_VERSION_RAW" "$RUM_VERSION")
    fi

    echo "[entrypoint] loaded config from $CONFIG_FILE"
else
    # 没有配置文件时，若有 BUILD_VERSION，也把它作为 rum.version 的兜底值
    if [ -n "$BUILD_VERSION" ]; then
        RUM_VERSION='"'"$BUILD_VERSION"'"'
    fi
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
  },
  "rum": {
    "enabled": ${RUM_ENABLED},
    "id": ${RUM_ID},
    "uin": ${RUM_UIN},
    "spa": ${RUM_SPA},
    "report_api_speed": ${RUM_REPORT_API_SPEED},
    "report_asset_speed": ${RUM_REPORT_ASSET_SPEED},
    "env": ${RUM_ENV},
    "version": ${RUM_VERSION},
    "sample_rate": ${RUM_SAMPLE_RATE},
    "src": ${RUM_SRC}
  }
}
ENDJSON

echo "[entrypoint] wrote /app/config.json server.name='${APP_NAME}' apiserver.host='${APISERVER_HOST}' apiserver.path_prefix='${APISERVER_PATH_PREFIX}' rum.enabled=${RUM_ENABLED} rum.version=${RUM_VERSION}"

exec nginx -g 'daemon off;'
