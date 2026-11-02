@echo off
chcp 65001 >nul
echo ========================================================
echo   个人 AI 阅读助手 (Personal AI Reading Assistant)
echo ========================================================

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [INFO] 已根据 .env.example 自动生成默认 .env 配置文件
    )
)

if not exist "data" (
    mkdir data
)

echo [INFO] 正在启动服务，请访问: http://127.0.0.1:8000
python run.py
