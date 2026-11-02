"""Persistence and user workflows exercised at the public HTTP boundary."""

from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient


def create_topic(client, name="阅读方法"):
    response = client.post("/api/topics", json={"name": name, "description": "比较不同阅读方法"})
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_public_configuration_do_not_expose_secrets(client):
    assert client.get("/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["mode"] == "demo"
    assert config["max_text_length"] == 100_000
    assert "api_key" not in config and "access_token" not in config


def test_complete_reading_workflow_survives_new_client(client, make_article, app_settings):
    topic = create_topic(client)
    article = make_article(topic_id=topic["id"])
    assert article["topic_id"] == topic["id"]
    assert article["mode"] == "demo" and article["error"] is None
    assert article["word_count"] > 0
    assert set(article["summary"]) == {"core_points", "arguments", "author_stance", "insights", "caveats"}
    assert "[p" in str(article["summary"])
    assert "演示" in str(article["summary"]["caveats"])
    response = client.post(f"/api/articles/{article['id']}/messages", json={"question": "这个观点有什么漏洞？"})
    assert response.status_code == 201
    pair = response.json()
    assert pair["user"]["role"] == "user"
    assert pair["assistant"]["role"] == "assistant"
    assert "演示" in pair["assistant"]["content"]
    assert len(client.get(f"/api/articles/{article['id']}/messages").json()) == 2
    app, _ = app_settings
    with TestClient(app) as reopened:
        assert reopened.get(f"/api/articles/{article['id']}").json()["summary"] == article["summary"]
        assert len(reopened.get(f"/api/articles/{article['id']}/messages").json()) == 2
        assert reopened.get("/api/topics").json()[0]["article_count"] == 1


def test_search_favorite_and_pagination(client, make_article):
    first = make_article(title="证据审查")
    second = make_article(title="包含字面符号 %_ 的标题")
    assert client.patch(f"/api/articles/{first['id']}", json={"favorite": True}).status_code == 200
    favorite = client.get("/api/articles", params={"favorite": "true"}).json()
    assert [item["id"] for item in favorite["items"]] == [first["id"]]
    # Search must treat SQL wildcard characters as literal input.
    result = client.get("/api/articles", params={"q": "%_"}).json()
    assert result["total"] == 1 and result["items"][0]["id"] == second["id"]
    assert client.get("/api/articles", params={"q": "' OR 1=1 --"}).json()["total"] == 0
    page = client.get("/api/articles", params={"limit": 1, "offset": 1}).json()
    assert len(page["items"]) == 1 and page["total"] == 2


@pytest.mark.parametrize("payload", [
    {}, {"text": "过短"}, {"text": " " * 30}, {"url": "https://example.com", "text": "正文" * 20},
    {"text": "字" * 100_001}, {"text": "\x00" * 20}, {"text": "有效正文" * 10, "unexpected_field": True},
])
def test_invalid_article_inputs_do_not_create_records(client, payload):
    response = client.post("/api/articles", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert client.get("/api/articles").json()["total"] == 0


def test_bad_topic_reference_does_not_create_article(client, make_article, article_text):
    response = client.post("/api/articles", json={"text": article_text, "topic_id": "missing"})
    assert response.status_code == 404
    assert client.get("/api/articles").json()["total"] == 0


def test_link_import_uses_extracted_title_and_preserves_source_url(client, article_text, monkeypatch):
    from backend import main

    monkeypatch.setattr(main, "fetch_article", lambda url: ("网页文章标题", article_text))
    response = client.post("/api/articles", json={"url": "https://article.example/read"})
    assert response.status_code == 201
    article = response.json()
    assert article["url"] == "https://article.example/read"
    assert article["title"] == "网页文章标题"
    assert article["text"] == article_text and article["summary"]


def test_failed_link_extraction_leaves_no_empty_article(client, monkeypatch):
    from backend import main

    def fail(_url):
        raise main.ExtractionError("无法读取网页，请粘贴正文")

    monkeypatch.setattr(main, "fetch_article", fail)
    response = client.post("/api/articles", json={"url": "https://article.example/read"})
    assert response.status_code == 422 and "粘贴正文" in response.json()["detail"]
    assert client.get("/api/articles").json()["total"] == 0


def test_topic_rename_uniqueness_and_delete_preserve_article(client, make_article):
    topic = create_topic(client)
    article = make_article(topic_id=topic["id"])
    renamed = client.patch(f"/api/topics/{topic['id']}", json={"name": "阅读与判断", "description": "新说明"})
    assert renamed.status_code == 200 and renamed.json()["article_count"] == 1
    assert client.post("/api/topics", json={"name": "阅读与判断"}).status_code == 409
    assert client.delete(f"/api/topics/{topic['id']}").status_code == 204
    restored = client.get(f"/api/articles/{article['id']}").json()
    assert restored["topic_id"] is None and restored["text"] == article["text"]


def test_compare_selected_same_topic_articles_and_history(client, make_article):
    topic = create_topic(client)
    first = make_article(topic_id=topic["id"])
    second = make_article(title="比较阅读", topic_id=topic["id"])
    make_article(title="未参与对比", topic_id=topic["id"])
    selected = [first["id"], second["id"]]
    response = client.post(f"/api/topics/{topic['id']}/compare", json={"article_ids": selected})
    assert response.status_code == 201, response.text
    comparison = response.json()
    assert set(comparison["article_ids"]) == set(selected)
    assert comparison["mode"] == "demo"
    assert {item["article_id"] for item in comparison["result"]["differences"]} == set(selected)
    history = client.get(f"/api/topics/{topic['id']}/comparisons").json()
    assert history[0]["id"] == comparison["id"]


def test_compare_rejects_missing_duplicate_or_foreign_article(client, make_article):
    topic = create_topic(client)
    first = make_article(topic_id=topic["id"])
    foreign = make_article()
    endpoint = f"/api/topics/{topic['id']}/compare"
    for ids in ([first["id"]], [first["id"], first["id"]], [first["id"], foreign["id"]], [first["id"], "missing"]):
        assert client.post(endpoint, json={"article_ids": ids}).status_code == 422
    assert client.get(f"/api/topics/{topic['id']}/comparisons").json() == []


def test_article_delete_removes_conversations_and_related_comparison(client, make_article):
    topic = create_topic(client)
    first = make_article(topic_id=topic["id"])
    second = make_article(topic_id=topic["id"])
    client.post(f"/api/articles/{first['id']}/messages", json={"question": "概括一下"})
    client.post(f"/api/topics/{topic['id']}/compare", json={"article_ids": [first["id"], second["id"]]})
    assert client.delete(f"/api/articles/{first['id']}").status_code == 204
    assert client.get(f"/api/articles/{first['id']}").status_code == 404
    backup = client.get("/api/export").json()
    assert backup["messages"] == [] and backup["comparisons"] == []
    assert len(backup["articles"]) == 1


def test_ai_summary_failure_retains_article_for_retry(client, make_article, monkeypatch):
    from backend import ai

    original_summarize = ai.summarize

    def fail(*_args):
        raise ai.AIError("模型请求超时，请重试")

    monkeypatch.setattr(ai, "summarize", fail)
    article = make_article()
    assert article["summary"] is None
    assert "超时" in article["error"]
    assert client.get(f"/api/articles/{article['id']}").status_code == 200
    monkeypatch.setattr(ai, "summarize", original_summarize)
    retry = client.post(f"/api/articles/{article['id']}/summarize").json()
    assert retry["summary"] is not None and retry["error"] is None


def test_failed_regeneration_keeps_prior_summary_and_provenance(client, make_article, monkeypatch):
    from backend import ai, main

    article = make_article()
    monkeypatch.setattr(main, "settings", replace(main.settings, ai_mode="ai", api_key="test-key"))

    def fail(*_args):
        raise ai.AIError("模型服务不可用")

    monkeypatch.setattr(ai, "summarize", fail)
    retried = client.post(f"/api/articles/{article['id']}/summarize").json()
    assert retried["summary"] == article["summary"]
    assert retried["mode"] == "demo" and retried["error"]


def test_failed_chat_does_not_save_half_a_turn(client, make_article, monkeypatch):
    from backend import ai

    article = make_article()

    def fail(*_args):
        raise ai.AIError("模型限流")

    monkeypatch.setattr(ai, "answer", fail)
    response = client.post(f"/api/articles/{article['id']}/messages", json={"question": "继续解释"})
    assert response.status_code == 502
    assert client.get(f"/api/articles/{article['id']}/messages").json() == []


def test_export_restore_roundtrip_is_idempotent(client, make_article):
    topic = create_topic(client)
    first, second = make_article(topic_id=topic["id"]), make_article(topic_id=topic["id"])
    client.post(f"/api/articles/{first['id']}/messages", json={"question": "这和认知负荷理论有什么关系？"})
    client.post(f"/api/topics/{topic['id']}/compare", json={"article_ids": [first["id"], second["id"]]})
    backup = client.get("/api/export").json()
    assert backup["version"] == 1 and len(backup["messages"]) == 2
    client.delete(f"/api/articles/{first['id']}")
    client.delete(f"/api/articles/{second['id']}")
    client.delete(f"/api/topics/{topic['id']}")
    imported = client.post("/api/import", json=backup)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == {"topics": 1, "articles": 2, "messages": 2, "comparisons": 1}
    replay = client.post("/api/import", json=backup).json()
    assert sum(replay["imported"].values()) == 0 and replay["skipped"] == 6
    restored = client.get("/api/export").json()
    for table in ("topics", "articles", "messages", "comparisons"):
        assert restored[table] == backup[table]


def test_import_conflict_rolls_back_every_record(client):
    create_topic(client, name="existing-name")
    backup = {
        "version": 1, "articles": [], "messages": [], "comparisons": [],
        "topics": [
            {"id": "new-first", "name": "should-roll-back", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "new-conflict", "name": "existing-name", "created_at": "2026-01-01T00:00:00Z"},
        ],
    }
    assert client.post("/api/import", json=backup).status_code == 409
    assert [topic["name"] for topic in client.get("/api/topics").json()] == ["existing-name"]


def test_import_does_not_overwrite_existing_article(client, make_article):
    article = make_article()
    backup = client.get("/api/export").json()
    client.patch(f"/api/articles/{article['id']}", json={"title": "本地更新后的标题"})
    result = client.post("/api/import", json=backup)
    assert result.status_code == 200 and result.json()["skipped"] == 1
    assert client.get(f"/api/articles/{article['id']}").json()["title"] == "本地更新后的标题"


def test_invalid_backup_references_are_rejected_atomically(client, make_article):
    make_article()
    backup = client.get("/api/export").json()
    backup["articles"][0]["id"] = "new-article"
    backup["articles"][0]["topic_id"] = "missing-topic"
    before = client.get("/api/articles").json()["total"]
    assert client.post("/api/import", json=backup).status_code == 422
    assert client.get("/api/articles").json()["total"] == before
    backup["articles"][0]["topic_id"] = None
    backup["articles"].append(deepcopy(backup["articles"][0]))
    assert client.post("/api/import", json=backup).status_code == 422
    assert client.get("/api/articles").json()["total"] == before


@pytest.mark.parametrize("field,value", [
    ("id", "../route-escape"),
    ("id", "article%2Ffragment#value"),
    ("created_at", "not-a-date"),
    ("updated_at", "2026-10-30T00:00:00"),
    ("url", "javascript:alert(1)"),
    ("url", "https://user:password@example.com/article"),
    ("url", "https://example.com:8080/article"),
    ("url", "https://example.com/article\r\nInjected:header"),
])
def test_unsafe_backup_fields_do_not_partially_import(client, make_article, field, value):
    make_article()
    before = client.get("/api/export").json()
    backup = deepcopy(before)
    backup["topics"] = [{"id": "new-backup-topic", "name": "must-not-import", "created_at": "2026-10-30T00:00:00Z"}]
    backup["articles"][0]["id"] = "new-backup-article"
    backup["articles"][0]["topic_id"] = "new-backup-topic"
    backup["articles"][0][field] = value
    response = client.post("/api/import", json=backup)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], str)
    after = client.get("/api/export").json()
    for table in ("topics", "articles", "messages", "comparisons"):
        assert after[table] == before[table]


def test_optional_access_token_protects_api_and_docs(client, monkeypatch):
    from backend import main

    monkeypatch.setattr(main, "settings", replace(main.settings, access_token="private-test-token"))
    for path in ("/api/config", "/api/export", "/docs", "/openapi.json"):
        assert client.get(path).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/api/config", headers={"X-Access-Token": "wrong"}).status_code == 401
    assert client.get("/api/config", headers={"X-Access-Token": "private-test-token"}).status_code == 200
    assert client.get("/api/config", headers={"Authorization": "Bearer private-test-token"}).status_code == 200


def test_cross_site_write_is_rejected_and_same_origin_is_accepted(client):
    body = {"name": "origin-check"}
    assert client.post("/api/topics", json=body, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/topics", json=body, headers={"Origin": "http://testserver"}).status_code == 201
    response = client.get("/api/config")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_request_body_limit_is_applied_before_json_parsing(client, monkeypatch):
    from backend import main

    monkeypatch.setattr(main, "MAX_BODY_BYTES", 100)
    response = client.post("/api/import", content=b"x" * 101, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert "detail" in response.json()


@pytest.mark.parametrize("path", ["/api/articles/missing", "/api/articles/missing/messages", "/api/topics/missing/comparisons"])
def test_missing_records_return_readable_errors(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
