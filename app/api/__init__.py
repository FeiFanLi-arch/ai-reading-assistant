"""API 路由蓝图注册模块"""

from __future__ import annotations

from flask import Flask


def register_api_blueprints(app: Flask) -> None:
    """将所有 RESTful API 蓝图注册到 Flask 应用实例"""
    from app.api.articles import articles_bp
    from app.api.system import system_bp
    from app.api.topics import topics_bp

    app.register_blueprint(articles_bp, url_prefix="/api/articles")
    app.register_blueprint(topics_bp, url_prefix="/api/topics")
    app.register_blueprint(system_bp, url_prefix="/api/system")
