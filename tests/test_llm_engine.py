"""
AI 结构化摘要、批判性追问与多文章主题对比引擎单元测试
"""

from __future__ import annotations

from app.services.llm_service import (
    answer_article_question,
    generate_article_summary,
    generate_topic_comparison,
)


SAMPLE_TEXT = """
第一性原理（First Principles Thinking）的核心在于回归事物最基本的条件，将其拆分成各要素进行解构分析，从而找到实现目标的最优路径。
相比之下，类比思维（Analogical Thinking）则是基于他人已有的实践做微调，虽然在成熟市场短期风险较低，但在技术范式转移期极易陷入路径依赖。
研究数据显示，超过 75% 的颠覆性创新企业在进行产品定义时，都主动质疑了行业沿用十余年的成本假设。
因此，产品团队在启动新项目时，应该首先列出当前方案的三个隐含前提，并逐一验证其在物理或经济规律上是否真正不可突破。
""".strip()


def test_generate_article_summary_structure():
    summary, tags = generate_article_summary(
        title="第一性原理与创新解构",
        content=SAMPLE_TEXT,
        session=None,
    )
    assert isinstance(summary, dict)
    assert summary.get("one_sentence_summary")
    assert len(summary.get("core_viewpoints", [])) >= 1
    assert len(summary.get("key_arguments", [])) >= 1
    assert "overall_tone" in summary.get("author_stance", {})
    assert len(summary.get("actionable_insights", [])) >= 1
    assert len(tags) >= 1


def test_answer_article_question_handles_flaws_and_theory_queries():
    summary, _ = generate_article_summary("第一性原理与创新解构", SAMPLE_TEXT)

    # 1. 追问漏洞
    ans_flaw, _ = answer_article_question(
        title="第一性原理与创新解构",
        content=SAMPLE_TEXT,
        summary=summary,
        history=[],
        question="这个观点有什么潜在漏洞？",
        quoted_text="类比思维在技术范式转移期极易陷入路径依赖",
    )
    assert "批判性审视" in ans_flaw or "漏洞" in ans_flaw
    assert "类比思维" in ans_flaw

    # 2. 追问与某理论的关系
    ans_theory, _ = answer_article_question(
        title="第一性原理与创新解构",
        content=SAMPLE_TEXT,
        summary=summary,
        history=[],
        question="和熊彼特创新理论有什么关系？",
    )
    assert "熊彼特创新" in ans_theory


def test_generate_topic_comparison_synthesizes_multiple_articles():
    s1, t1 = generate_article_summary("第一性原理的优势", SAMPLE_TEXT)
    s2, t2 = generate_article_summary(
        "渐进式改良的护城河",
        "在商业实践中，盲目追求颠覆式创新往往伴随高达 90% 的失败率。通过持续微创新与用户反馈迭代，企业可以用更低试错成本建立复利优势。",
    )
    articles = [
        {"id": 1, "title": "第一性原理的优势", "author": "作者A", "raw_content": SAMPLE_TEXT, "summary": s1, "tags": t1},
        {"id": 2, "title": "渐进式改良的护城河", "author": "作者B", "raw_content": "...", "summary": s2, "tags": t2},
    ]
    comp = generate_topic_comparison(
        topic_name="创新方法论对比：颠覆解构 vs 渐进迭代",
        topic_desc="探讨不同阶段企业的创新路径选择",
        articles=articles,
    )
    assert comp.get("overview")
    assert len(comp.get("consensus_points", [])) >= 1
    assert len(comp.get("disagreements", [])) >= 1
    assert len(comp.get("comparison_matrix", [])) == 2
    assert len(comp.get("synthesized_actions", [])) >= 1
