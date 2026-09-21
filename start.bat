@echo off
chcp 65001 >nul
REM 一键启动（Windows）：装依赖 → 装浏览器 → 打开 http://localhost:8777
cd /d "%~dp0"

echo ==^> 安装 Python 依赖
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo ==^> 检查浏览器（首次约需下载 100MB）
python -m playwright install chromium

echo ==^> 启动服务：http://localhost:8777
python app.py
