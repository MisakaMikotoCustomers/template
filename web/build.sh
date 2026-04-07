#!/bin/bash
# 前端构建脚本
# 用法: ./build.sh <tag>
# 示例: ./build.sh v1.2.3
#
# tag 作为文件版本标识，防止浏览器缓存旧文件

set -e

TAG="${1:-dev}"

echo "Building frontend with tag: ${TAG}"

# 安装依赖
npm ci --prefer-offline

# 执行 Vite 构建，注入 BUILD_TAG 环境变量
VITE_BUILD_TAG="${TAG}" npm run build

echo "Build complete. Output: dist/"
echo "Version tag: ${TAG}"
