#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  个人 AI 阅读助手 (Personal AI Reading Assistant)"
echo "========================================================"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[INFO] 已根据 .env.example 自动生成默认 .env 配置文件"
fi

mkdir -p data

echo "[INFO] 正在启动服务，请访问: http://127.0.0.1:8000"
python3 run.py
