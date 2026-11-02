"""
个人 AI 阅读助手 - 应用启动入口 (Entrypoint)

启动方式：
    python run.py
或者通过 Gunicorn (生产环境/Docker)：
    gunicorn -w 2 --threads 4 -b 0.0.0.0:8000 run:app
"""

from __future__ import annotations

from app import create_app
from app.config import Config

app = create_app()

if __name__ == "__main__":
    print(f"🚀 个人 AI 阅读助手已启动: http://127.0.0.1:{Config.APP_PORT}")
    app.run(
        host=Config.APP_HOST,
        port=Config.APP_PORT,
        debug=(Config.APP_ENV == "development"),
    )
