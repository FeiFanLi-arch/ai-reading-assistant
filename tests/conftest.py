"""All API tests use temporary databases and never call a paid provider."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_settings(tmp_path, monkeypatch):
    from backend import ai, config, db, main

    settings = replace(
        config.settings,
        db_path=str(tmp_path / "test-reader.db"),
        ai_mode="demo",
        api_key="",
        access_token="",
    )
    for module in (ai, config, db, main):
        monkeypatch.setattr(module, "settings", settings)
    return main.app, settings


@pytest.fixture
def client(app_settings):
    app, _ = app_settings
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def article_text():
    return (
        "持续阅读可以帮助人们理解复杂问题，但阅读数量不应该成为唯一目标。"
        "作者认为，主动提问和复述比机械记录页数更重要。\n\n"
        "例如，一项课堂观察发现，先写下问题再阅读的学生更容易发现论证的缺口。"
        "不过，这个观察没有随机分组，也不能证明因果关系。\n\n"
        "因此，读者可以在每次阅读后写下一个观点、一条证据和一个反例。"
        "一周后重新检查这些笔记，判断原来的理解是否需要修正。"
    )


@pytest.fixture
def make_article(client, article_text):
    def create(**overrides):
        payload = {"title": "如何进行主动阅读", "text": article_text, **overrides}
        response = client.post("/api/articles", json=payload)
        assert response.status_code in (200, 201), response.text
        return response.json()

    return create
