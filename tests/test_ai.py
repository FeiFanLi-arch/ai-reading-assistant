"""The real AI branch is exercised through an in-memory HTTP transport."""

import json
from dataclasses import replace

import httpx
import pytest

from backend import ai


SUMMARY = {
    "core_points": ["主动阅读强调提问与复述。[p1]"],
    "arguments": [{"point": "课堂观察提供有限支持。", "evidence": "研究未随机分组。[p2]"}],
    "author_stance": {"position": "支持主动阅读", "tone": "审慎", "confidence": "中等：依据为原文论述"},
    "insights": ["在笔记中保留反例。"],
    "caveats": ["观察不能证明因果。"],
}


@pytest.fixture
def provider(monkeypatch):
    original_client = httpx.Client
    settings = replace(ai.settings, ai_mode="ai", api_key="unit-test-only-key", base_url="https://provider.example/v1")
    monkeypatch.setattr(ai, "settings", settings)

    def install(content=None, status=200, handler=None, finish_reason="stop"):
        requests = []

        def respond(request):
            requests.append(request)
            if handler:
                return handler(request)
            payload = {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}
            return httpx.Response(status, json=payload)

        transport = httpx.MockTransport(respond)
        monkeypatch.setattr(ai.httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
        return requests

    return install


def test_real_summary_requests_json_and_validates_schema(provider, article_text):
    requests = provider(json.dumps(SUMMARY, ensure_ascii=False))
    result = ai.summarize(article_text, "主动阅读")
    assert result == SUMMARY
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://provider.example/v1/chat/completions"
    body = json.loads(request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert "[p1]" in body["messages"][-1]["content"]
    assert "[p2]" in body["messages"][-1]["content"]
    assert body["messages"][0]["role"] == "system"


@pytest.mark.parametrize("content", ["not JSON", "{}", json.dumps({**SUMMARY, "arguments": []})])
def test_invalid_provider_output_is_not_persistable_summary(provider, article_text, content):
    provider(content)
    with pytest.raises(ai.AIError):
        ai.summarize(article_text, "主动阅读")


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_provider_errors_never_fall_back_to_demo(provider, article_text, status):
    requests = provider("pretend response", status=status)
    with pytest.raises(ai.AIError):
        ai.summarize(article_text, "主动阅读")
    assert len(requests) == 1


def test_provider_timeout_becomes_safe_user_error(provider, article_text):
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    provider(handler=timeout)
    with pytest.raises(ai.AIError, match="超时"):
        ai.summarize(article_text, "主动阅读")


def test_forced_ai_without_key_fails_before_network(monkeypatch, article_text):
    monkeypatch.setattr(ai, "settings", replace(ai.settings, ai_mode="ai", api_key=""))

    def unexpected_client(**_kwargs):
        pytest.fail("Missing credentials must not result in a network request")

    monkeypatch.setattr(ai.httpx, "Client", unexpected_client)
    with pytest.raises(ai.AIError, match="AI_API_KEY"):
        ai.summarize(article_text, "主动阅读")


def test_model_truncation_is_reported_as_error(provider, article_text):
    provider(json.dumps(SUMMARY), finish_reason="length")
    with pytest.raises(ai.AIError, match="长度"):
        ai.summarize(article_text, "主动阅读")


def test_long_input_discloses_excerpt_in_prompt_and_result(provider, monkeypatch):
    monkeypatch.setattr(ai, "settings", replace(ai.settings, ai_context_chars=200))
    requests = provider(json.dumps(SUMMARY, ensure_ascii=False))
    result = ai.summarize("开头论述。" * 300 + "\n\n结尾论述。" * 300, "长文章")
    assert "范围限制" in result["caveats"][0]
    assert "节选" in json.loads(requests[0].content)["messages"][-1]["content"]


def test_chat_includes_article_and_previous_turn_without_structured_format(provider, article_text):
    requests = provider("可以先检验观察结果是否存在选择偏差。[p2]")
    history = [{"role": "user", "content": "作者支持什么？"}, {"role": "assistant", "content": "作者支持主动阅读。"}]
    result = ai.answer(article_text, "主动阅读", "这个观点有什么漏洞？", history)
    assert "[p2]" in result
    body = json.loads(requests[0].content)
    assert "response_format" not in body
    assert any(message["content"] == history[0]["content"] for message in body["messages"])
    assert body["messages"][-1]["content"] == "这个观点有什么漏洞？"


def test_comparison_rejects_missing_article_identity(provider, article_text):
    provider(json.dumps({
        "overview": "两篇文章比较", "common_ground": ["都讨论阅读"],
        "differences": [{"article_id": "wrong", "title": "误配", "position": "观点"},
                        {"article_id": "b", "title": "第二篇", "position": "观点"}],
        "contradictions": ["没有明确矛盾"], "insights": ["核查证据"],
    }, ensure_ascii=False))
    with pytest.raises(ai.AIError, match="文章"):
        ai.compare([{"id": "a", "title": "第一篇", "text": article_text}, {"id": "b", "title": "第二篇", "text": article_text}])
