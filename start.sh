#!/usr/bin/env bash
# 一键启动（macOS / Linux）：装依赖 → 装浏览器 → 打开 http://localhost:8777
set -e
cd "$(dirname "$0")"

echo "==> 安装 Python 依赖"
python3 -m pip install -q --upgrade pip
python3 -m pip install -q -r requirements.txt

echo "==> 检查浏览器（首次约需下载 100MB）"
python3 -m playwright install chromium || true

echo "==> 启动服务：http://localhost:8777"
python3 app.py
