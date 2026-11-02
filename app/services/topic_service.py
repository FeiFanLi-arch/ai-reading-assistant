"""
多文章研究「主题」与对比综述业务服务 (Topic Management & Cross-Article Synthesis Service)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Article, Topic, TopicArticle, TopicMessage
from app.services.llm_service import answer_topic_question, generate_topic_comparison


class TopicServiceError(Exception):
    """主题业务处理异常"""
    pass


def create_topic(
    session: Session,
    name: str,
    description: str = "",
    color: str = "#4f46e5",
    article_ids: list[int] | None = None,
    auto_compare: bool = True,
) -> Topic:
    """创建新主题，可选关联初始文章并立即生成对比总结"""
    clean_name = (name or "").strip()
    if not clean_name:
        raise TopicServiceError("主题名称不能为空。")

    topic = Topic(
        name=clean_name[:200],
        description=(description or "").strip(),
        color=(color or "#4f46e5").strip(),
    )
    session.add(topic)
    session.flush()

    if article_ids:
        for aid in dict.fromkeys(article_ids):
            article = session.get(Article, int(aid))
            if article is not None:
                session.add(TopicArticle(topic_id=topic.id, article_id=article.id))
        session.flush()
        session.refresh(topic)

    if auto_compare and len(topic.article_links) >= 1:
        run_topic_comparison(session, topic.id)

    return topic


def update_topic_articles(
    session: Session,
    topic_id: int,
    article_ids: list[int],
    auto_compare: bool = False,
) -> Topic:
    """全量同步或更新某主题下的文章列表"""
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicServiceError("未找到对应的研究主题。")

    # 清空旧有关联并重建
    session.query(TopicArticle).filter(TopicArticle.topic_id == topic.id).delete()
    session.flush()

    for aid in dict.fromkeys(article_ids):
        article = session.get(Article, int(aid))
        if article is not None:
            session.add(TopicArticle(topic_id=topic.id, article_id=article.id))
    session.flush()
    session.refresh(topic)

    if auto_compare and len(topic.article_links) >= 1:
        run_topic_comparison(session, topic.id)

    return topic


def add_article_to_topic(session: Session, topic_id: int, article_id: int) -> Topic:
    """将单篇文章加入指定主题"""
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicServiceError("未找到对应的研究主题。")
    article = session.get(Article, article_id)
    if article is None:
        raise TopicServiceError("未找到对应的文章。")

    existing = (
        session.query(TopicArticle)
        .filter(TopicArticle.topic_id == topic_id, TopicArticle.article_id == article_id)
        .first()
    )
    if existing is None:
        session.add(TopicArticle(topic_id=topic_id, article_id=article_id))
        session.flush()
        session.refresh(topic)
    return topic


def remove_article_from_topic(session: Session, topic_id: int, article_id: int) -> Topic:
    """从指定主题中移除单篇文章"""
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicServiceError("未找到对应的研究主题。")

    session.query(TopicArticle).filter(
        TopicArticle.topic_id == topic_id, TopicArticle.article_id == article_id
    ).delete()
    session.flush()
    session.refresh(topic)
    return topic


def run_topic_comparison(session: Session, topic_id: int) -> Topic:
    """针对主题下收录的所有文章执行横向对比与综合提炼"""
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicServiceError("未找到对应的研究主题。")

    articles_data = [
        link.article.to_dict(include_details=True)
        for link in topic.article_links
        if link.article is not None
    ]
    if not articles_data:
        raise TopicServiceError("该主题下尚未添加任何文章，请先添加至少 1~2 篇文章后再生成对比总结。")

    comparison_result = generate_topic_comparison(
        topic_name=topic.name,
        topic_desc=topic.description,
        articles=articles_data,
        session=session,
    )
    topic.comparison = comparison_result
    session.flush()
    return topic


def ask_topic_followup(
    session: Session,
    topic_id: int,
    question: str,
) -> tuple[TopicMessage, TopicMessage]:
    """针对整个主题下的多篇文章发起跨篇追问"""
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicServiceError("未找到对应的研究主题。")

    clean_q = (question or "").strip()
    if not clean_q:
        raise TopicServiceError("追问问题不能为空。")

    articles_data = [
        link.article.to_dict(include_details=True)
        for link in topic.article_links
        if link.article is not None
    ]
    if not articles_data:
        raise TopicServiceError("该主题下暂无文章，请先添加文章后再进行跨篇追问。")

    history_dicts = [m.to_dict() for m in topic.messages]
    user_msg = TopicMessage(
        topic_id=topic.id,
        role="user",
        content=clean_q,
        engine_used="user",
    )
    session.add(user_msg)
    session.flush()

    answer_md, engine_used = answer_topic_question(
        topic_name=topic.name,
        articles=articles_data,
        comparison=topic.comparison,
        history=history_dicts,
        question=clean_q,
        session=session,
    )
    assistant_msg = TopicMessage(
        topic_id=topic.id,
        role="assistant",
        content=answer_md,
        engine_used=engine_used,
    )
    session.add(assistant_msg)
    session.flush()
    return user_msg, assistant_msg


def export_topic_markdown(topic: Topic) -> str:
    """将多文章主题对比总结导出为结构化 Markdown 研究报告"""
    comp: dict[str, Any] = topic.comparison or {}
    articles = [link.article for link in topic.article_links if link.article is not None]

    lines = [
        f"# 🗂️ 主题跨文献对比研究报告：{topic.name}",
        "",
        f"- **主题描述**：{topic.description or '无'}",
        f"- **收录文章数**：{len(articles)} 篇",
        f"- **对比报告生成时间**：{comp.get('generated_at', '未生成')}",
        "",
        "## 一、收录文献清单",
        "",
    ]
    for idx, art in enumerate(articles, start=1):
        lines.append(
            f"{idx}. **《{art.title}》**（{art.author or art.site_name or '未知来源'} · {art.word_count} 字）"
        )
    lines.append("")

    if comp:
        lines.extend(
            [
                "## 二、主题全景综述 (Executive Overview)",
                "",
                f"> {comp.get('overview', '')}",
                "",
                "## 三、跨文章核心共识 (Consensus Points)",
                "",
            ]
        )
        for idx, cp in enumerate(comp.get("consensus_points", []), start=1):
            lines.append(f"### {idx}. {cp.get('point', '')}")
            lines.append(f"{cp.get('detail', '')}")
            lines.append("")

        lines.extend(
            [
                "## 四、关键分歧与张力对比 (Disagreements & Tensions)",
                "",
            ]
        )
        for idx, dis in enumerate(comp.get("disagreements", []), start=1):
            lines.append(f"### {idx}. {dis.get('dimension', '')}")
            lines.append(f"- **分歧核心**：{dis.get('conflict_summary', '')}")
            for pos in dis.get("positions", []):
                lines.append(f"  - **《{pos.get('article_title', '')}》**：{pos.get('stance', '')}")
            lines.append("")

        lines.extend(
            [
                "## 五、多维横向对比矩阵 (Comparison Matrix)",
                "",
                "| 文章标题 | 作者/来源 | 态度基调 | 论证方法 | 核心论点 | 独特增量价值 | 视角局限性 |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for m in comp.get("comparison_matrix", []):
            lines.append(
                f"| 《{m.get('article_title', '')}》 | {m.get('author', '')} | {m.get('stance_tone', '')} | "
                f"{m.get('methodology', '')} | {m.get('core_thesis', '')} | {m.get('unique_value', '')} | {m.get('limitation', '')} |"
            )
        lines.append("")

        lines.extend(
            [
                "## 六、视角互补与认知升级路径 (Complementary Synthesis)",
                "",
                comp.get("complementary_insights", ""),
                "",
                "## 七、跨文章综合行动建议 (Synthesized Action Plan)",
                "",
            ]
        )
        for idx, act in enumerate(comp.get("synthesized_actions", []), start=1):
            lines.append(
                f"{idx}. **{act.get('title', '')}**（*启发自：《{act.get('source_inspiration', '')}》*）"
            )
            lines.append(f"   - {act.get('detail', '')}")
        lines.append("")

    if topic.messages:
        lines.extend(
            [
                "## 八、主题跨篇追问记录 (Topic Q&A)",
                "",
            ]
        )
        for msg in topic.messages:
            if msg.role == "user":
                lines.append(f"### 🙋 跨篇提问：{msg.content}")
                lines.append("")
            else:
                lines.append(msg.content)
                lines.append("")

    return "\n".join(lines)
