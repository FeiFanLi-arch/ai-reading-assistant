"""
全链路 REST API 端到端集成测试 (End-to-End API Integration Tests)
"""

from __future__ import annotations


def test_full_reading_and_topic_comparison_workflow(client):
    # 1. 健康检查与初始空状态验证
    health_resp = client.get("/api/system/health")
    assert health_resp.status_code == 200
    assert health_resp.get_json()["status"] == "ok"

    # 2. 导入第 1 篇文章（粘贴文本）
    art1_payload = {
        "source_type": "text",
        "title": "深度工作：在分心时代建立认知护城河",
        "author": "卡尔·纽波特",
        "raw_text": (
            "深度工作（Deep Work）是指在无干扰的状态下专注进行职业活动，使个人的认知能力达到极限。"
            "研究显示，频繁切换任务会产生严重的注意力残留效应，导致核心产出效率下降 40% 以上。"
            "因此，知识工作者必须每天划定至少 90 分钟的完全断网深度工作时间块，并建立严格的停工仪式。"
        ),
    }
    resp1 = client.post("/api/articles", json=art1_payload)
    assert resp1.status_code == 201
    art1 = resp1.get_json()
    assert art1["title"] == "深度工作：在分心时代建立认知护城河"
    assert "summary" in art1
    assert len(art1["summary"]["core_viewpoints"]) >= 1
    assert len(art1["summary"]["key_arguments"]) >= 1
    assert "author_stance" in art1["summary"]
    assert len(art1["summary"]["actionable_insights"]) >= 1

    # 3. 对第 1 篇文章发起追问
    ask_resp = client.post(
        f"/api/articles/{art1['id']}/ask",
        json={
            "question": "这个观点有什么漏洞？如果工作性质要求随时响应消息怎么办？",
            "quoted_text": "每天划定至少 90 分钟的完全断网深度工作时间块",
        },
    )
    assert ask_resp.status_code == 200
    ask_data = ask_resp.get_json()
    assert ask_data["user_message"]["role"] == "user"
    assert ask_data["assistant_message"]["role"] == "assistant"
    assert len(ask_data["assistant_message"]["content"]) > 30

    # 4. 更新个人批注与星标收藏
    patch_resp = client.patch(
        f"/api/articles/{art1['id']}",
        json={"is_favorite": True, "user_notes": "每天上午 9:30-11:00 执行深度工作块。"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.get_json()["is_favorite"] is True

    # 5. 导入第 2 篇文章
    art2_payload = {
        "source_type": "text",
        "title": "敏捷协作网络：为什么过度封闭专注会损害团队创新",
        "author": "组织行为学评论",
        "raw_text": (
            "在高度不确定性的创新型组织中，个体长时间封闭式办公往往导致信息孤岛与方向偏离。"
            "通过对 50 个高绩效研发团队的追踪发现，高频的非正式高频沟通与即时微反馈能将跨部门协同摩擦降低 35%。"
            "与其追求与世隔绝的个人专注，团队更应该设计高信噪比的异步文档与固定同步窗口。"
        ),
    }
    resp2 = client.post("/api/articles", json=art2_payload)
    assert resp2.status_code == 201
    art2 = resp2.get_json()

    # 6. 创建多文章对比「主题」并自动生成对比总结
    topic_resp = client.post(
        "/api/topics",
        json={
            "name": "个人深度专注 vs 团队高频敏捷协同",
            "description": "探讨知识工作者在个人深度思考与团队实时响应之间的平衡策略",
            "color": "#059669",
            "article_ids": [art1["id"], art2["id"]],
            "auto_compare": True,
        },
    )
    assert topic_resp.status_code == 201
    topic_data = topic_resp.get_json()
    assert topic_data["article_count"] == 2
    assert topic_data["has_comparison"] is True
    assert len(topic_data["comparison"]["comparison_matrix"]) == 2
    assert len(topic_data["comparison"]["disagreements"]) >= 1

    # 7. 对主题发起跨文章追问
    topic_ask_resp = client.post(
        f"/api/topics/{topic_data['id']}/ask",
        json={"question": "这两篇文章在时间管理策略上的根本分歧是什么？如何折中结合？"},
    )
    assert topic_ask_resp.status_code == 200
    assert "深度工作" in topic_ask_resp.get_json()["assistant_message"]["content"]

    # 8. 验证历史记录搜索与导出 Markdown
    search_resp = client.get("/api/articles?search=注意力残留")
    assert search_resp.status_code == 200
    assert search_resp.get_json()["total"] == 1

    export_art_resp = client.get(f"/api/articles/{art1['id']}/export")
    assert export_art_resp.status_code == 200
    assert "一句话核心总结" in export_art_resp.get_json()["markdown"]

    export_topic_resp = client.get(f"/api/topics/{topic_data['id']}/export")
    assert export_topic_resp.status_code == 200
    assert "多维横向对比矩阵" in export_topic_resp.get_json()["markdown"]


def test_runtime_llm_settings_update(client):
    put_resp = client.put(
        "/api/system/llm-config",
        json={
            "provider": "local",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "temperature": 0.2,
        },
    )
    assert put_resp.status_code == 200
    cfg = put_resp.get_json()
    assert cfg["provider"] == "local"
    assert cfg["model"] == "deepseek-chat"
    assert cfg["active_mode"] == "heuristic"
