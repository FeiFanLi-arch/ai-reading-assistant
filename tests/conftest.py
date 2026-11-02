"""
Pytest 测试夹具配置 (Test Fixtures)
"""

from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture()
def app():
    """创建使用独立内存 SQLite 数据库的测试应用实例"""
    test_app = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": "sqlite:///:memory:",
            "SEED_DEMO_DATA": False,
        }
    )
    yield test_app


@pytest.fixture()
def client(app):
    """Flask 测试客户端"""
    return app.test_client()
