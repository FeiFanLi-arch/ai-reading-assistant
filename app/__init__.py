"""
Flask 应用工厂模块 (Application Factory)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, render_template

from app.api import register_api_blueprints
from app.config import Config
from app.database import init_db, session_scope
from app.services.seed_service import seed_initial_data_if_empty


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """创建并配置 Flask 应用实例"""
    web_dir = Path(__file__).resolve().parent / "web"
    app = Flask(
        __name__,
        template_folder=str(web_dir / "templates"),
        static_folder=str(web_dir / "static"),
        static_url_path="/static",
    )

    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    # 初始化数据库
    db_url = app.config.get("DATABASE_URL", Config.DATABASE_URL)
    init_db(db_url)

    # 首次启动时注入示例文章与对比主题（可通过 SEED_DEMO_DATA=false 关闭）
    if app.config.get("SEED_DEMO_DATA", Config.SEED_DEMO_DATA):
        with session_scope() as session:
            seed_initial_data_if_empty(session, force=False)

    # 注册所有 API 路由蓝图
    register_api_blueprints(app)

    # 注册前端单页工作台主入口
    @app.get("/")
    def index_view():
        return render_template("index.html")

    return app
