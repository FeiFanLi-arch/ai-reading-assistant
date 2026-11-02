"""
文章阅读与知识库管理业务服务 (Article Management & Reading Workflow Service)
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Article, ArticleMessage, Topic, TopicArticle
from app.services.llm_service import answer_article_question, generate_article_summary
from app.services.scraper_service import (
    ScraperError,
    clean_whitespace,
    compute_reading_stats,
    fetch_url_article,
)


class ArticleServiceError(Exception):
    """文章业务处理异常"""
    pass


def _infer_title_from_text(content: str) -> str:
    """当用户未填写标题而直接粘贴文本时，自动从首行或首句智能提炼标题"""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "未命名阅读笔记"
    first_line = re.sub(r"^#{1,6}\s*", "", lines[0]).strip()
    if len(first_line) <= 65:
        return first_line
    first_clause = re.split(r"[。！？.!?；;]", first_line)[0].strip()
    if 4 <= len(first_clause) <= 65:
        return first_clause
    return first_line[:56] + "…"


def create_article(
    session: Session,
    source_type: str,
    url: str | None = None,
    raw_text: str | None = None,
    title: str | None = None,
    author: str | None = None,
    topic_ids: list[int] | None = None,
) -> Article:
    """
    创建并解析一篇新文章：
    - 若 source_type == 'url'：自动抓取网页正文；若用户同时提供了备用文本且网页被反爬拦截，则平滑使用备用文本
    - 若 source_type in ('text', 'file')：直接清洗文本并计算字数与阅读时长
    - 自动调用 AI 引擎生成结构化摘要（核心观点、关键论据、作者态度、可行动洞察、核心概念）
    - 可选直接归入指定的「主题」列表
    """
    stype = (source_type or "text").lower().strip()
    cleaned_title = (title or "").strip()
    cleaned_author = (author or "").strip() or None
    cleaned_url = (url or "").strip() or None
    site_name: str | None = None

    if stype == "url":
        if not cleaned_url:
            raise ArticleServiceError("选择链接导入时，请输入有效的文章 URL。")
        try:
            extracted = fetch_url_article(cleaned_url)
            final_title = cleaned_title or extracted.title
            final_content = extracted.content
            site_name = extracted.site_name
            cleaned_author = cleaned_author or extracted.author
            word_count = extracted.word_count
            reading_minutes = extracted.reading_time_minutes
        except ScraperError as exc:
            # 如果用户同时粘贴了正文内容作为兜底，则继续处理
            if raw_text and len(raw_text.strip()) >= 20:
                final_content = clean_whitespace(raw_text)
                final_title = cleaned_title or _infer_title_from_text(final_content)
                word_count, reading_minutes = compute_reading_stats(final_content)
                site_name = "Web Article (Manual Fallback)"
            else:
                raise ArticleServiceError(str(exc)) from exc
    else:
        if not raw_text or len(raw_text.strip()) < 15:
            raise ArticleServiceError("粘贴的文章正文过短（至少需要 15 个字符），请输入完整的段落或文章。")
        final_content = clean_whitespace(raw_text)
        final_title = cleaned_title or _infer_title_from_text(final_content)
        word_count, reading_minutes = compute_reading_stats(final_content)
        site_name = "本地文件导入" if stype == "file" else "直接文本粘贴"

    summary_data, auto_tags = generate_article_summary(
        title=final_title,
        content=final_content,
        session=session,
    )

    article = Article(
        title=final_title,
        source_type=stype if stype in ("url", "text", "file") else "text",
        source_url=cleaned_url,
        site_name=site_name,
        author=cleaned_author,
        raw_content=final_content,
        word_count=word_count,
        reading_time_minutes=reading_minutes,
        reading_status="reading",
    )
    article.summary = summary_data
    article.tags = auto_tags

    session.add(article)
    session.flush()

    # 若指定了归属主题，建立关联
    if topic_ids:
        for tid in set(topic_ids):
            topic = session.get(Topic, int(tid))
            if topic is not None:
                session.add(TopicArticle(topic_id=topic.id, article_id=article.id))
        session.flush()

    return article


def list_articles(
    session: Session,
    search: str | None = None,
    tag: str | None = None,
    topic_id: int | None = None,
    favorite_only: bool = False,
    reading_status: str | None = None,
) -> list[dict[str, Any]]:
    """查询历史文章列表（支持关键词全文检索、标签过滤、主题过滤、收藏过滤、阅读状态过滤）"""
    query = session.query(Article)

    if favorite_only:
        query = query.filter(Article.is_favorite.is_(True))

    if reading_status and reading_status in ("unread", "reading", "completed"):
        query = query.filter(Article.reading_status == reading_status)

    if topic_id is not None:
        query = query.join(TopicArticle, TopicArticle.article_id == Article.id).filter(
            TopicArticle.topic_id == topic_id
        )

    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Article.title.ilike(kw),
                Article.raw_content.ilike(kw),
                Article.summary_json.ilike(kw),
                Article.tags_json.ilike(kw),
                Article.user_notes.ilike(kw),
            )
        )

    if tag and tag.strip():
        tag_kw = f'%"{tag.strip()}"%'
        query = query.filter(Article.tags_json.ilike(tag_kw))

    articles = query.order_by(Article.created_at.desc(), Article.id.desc()).all()
    return [a.to_dict(include_details=False) for a in articles]


def regenerate_summary(session: Session, article_id: int) -> Article:
    """使用当前最新 AI 引擎配置重新生成文章的结构化摘要"""
    article = session.get(Article, article_id)
    if article is None:
        raise ArticleServiceError("未找到对应的文章记录。")

    summary_data, auto_tags = generate_article_summary(
        title=article.title,
        content=article.raw_content,
        session=session,
    )
    article.summary = summary_data
    if not article.tags:
        article.tags = auto_tags
    session.flush()
    return article


def ask_followup_question(
    session: Session,
    article_id: int,
    question: str,
    quoted_text: str | None = None,
) -> tuple[ArticleMessage, ArticleMessage]:
    """对指定文章发起追问，持久化用户提问与 AI 回答并返回"""
    article = session.get(Article, article_id)
    if article is None:
        raise ArticleServiceError("未找到对应的文章记录。")

    clean_q = (question or "").strip()
    if not clean_q:
        raise ArticleServiceError("追问问题不能为空。")

    history_dicts = [m.to_dict() for m in article.messages]
    user_msg = ArticleMessage(
        article_id=article.id,
        role="user",
        content=clean_q,
        quoted_text=(quoted_text or "").strip() or None,
        engine_used="user",
    )
    session.add(user_msg)
    session.flush()

    answer_md, engine_used = answer_article_question(
        title=article.title,
        content=article.raw_content,
        summary=article.summary,
        history=history_dicts,
        question=clean_q,
        quoted_text=quoted_text,
        session=session,
    )

    assistant_msg = ArticleMessage(
        article_id=article.id,
        role="assistant",
        content=answer_md,
        quoted_text=None,
        engine_used=engine_used,
    )
    session.add(assistant_msg)
    session.flush()
    return user_msg, assistant_msg


def export_article_markdown(article: Article) -> str:
    """将单篇文章的结构化摘要、个人批注与追问记录导出为排版精美的 Markdown 读书笔记"""
    s = article.summary
    lines = [
        f"# 📖 深度阅读笔记：{article.title}",
        "",
        f"- **来源类型**：{article.source_type.upper()}",
        f"- **原始链接**：{article.source_url or '无（直接文本导入）'}",
        f"- **作者 / 站点**：{article.author or '未知'} / {article.site_name or '未知'}",
        f"- **字数与预计阅读**：{article.word_count} 字（约 {article.reading_time_minutes} 分钟）",
        f"- **标签**：{', '.join(f'`{t}`' for t in article.tags) if article.tags else '无'}",
        f"- **记录时间**：{article.created_at.strftime('%Y-%m-%d %H:%M') if article.created_at else ''}",
        "",
        "---",
        "",
        "## 一、一句话核心总结 (TL;DR)",
        "",
        f"> {s.get('one_sentence_summary', '暂无')}",
        "",
        "## 二、核心观点 (Core Viewpoints)",
        "",
    ]
    for idx, vp in enumerate(s.get("core_viewpoints", []), start=1):
        lines.append(f"### {idx}. {vp.get('title', '观点')} `重要度：{vp.get('importance', '高')}`")
        lines.append(f"{vp.get('detail', '')}")
        lines.append("")

    lines.append("## 三、关键论据与论证分析 (Key Arguments & Evidence)")
    lines.append("")
    for idx, arg in enumerate(s.get("key_arguments", []), start=1):
        lines.append(f"- **论据 {idx}（{arg.get('logic_type', '逻辑论证')}）**：{arg.get('claim', '')}")
        lines.append(f"  - **深度解析**：{arg.get('evidence', '')}")
        if arg.get("quote"):
            lines.append(f"  - **原文摘录**：*“{arg.get('quote')}”*")
    lines.append("")

    stance = s.get("author_stance", {})
    lines.extend(
        [
            "## 四、作者态度与立场审视 (Author's Stance)",
            "",
            f"- **整体基调**：{stance.get('overall_tone', '理性分析')}（客观度评估：{stance.get('objectivity_score', 80)}/100）",
            f"- **核心立场**：{stance.get('stance_description', '')}",
            f"- **潜在局限与隐含假设**：{stance.get('potential_bias', '')}",
            f"- **目标受众**：{stance.get('target_audience', '')}",
            "",
            "## 五、可行动洞察 (Actionable Insights)",
            "",
        ]
    )
    for idx, ins in enumerate(s.get("actionable_insights", []), start=1):
        lines.append(f"{idx}. **{ins.get('action', '')}**（`{ins.get('priority', '')}`）")
        lines.append(f"   - **具体方法**：{ins.get('scenario', '')}")
        lines.append(f"   - **预期成果**：{ins.get('expected_outcome', '')}")
    lines.append("")

    if article.user_notes and article.user_notes.strip():
        lines.extend(
            [
                "## 六、个人阅读批注与思考 (Personal Notes)",
                "",
                article.user_notes.strip(),
                "",
            ]
        )

    if article.messages:
        lines.extend(
            [
                "## 七、深度追问与思辨记录 (Follow-up Q&A)",
                "",
            ]
        )
        for msg in article.messages:
            if msg.role == "user":
                lines.append(f"### 🙋 追问：{msg.content}")
                if msg.quoted_text:
                    lines.append(f"> 引用片段：*“{msg.quoted_text}”*")
                lines.append("")
            else:
                lines.append(msg.content)
                lines.append("")
                lines.append("---")
                lines.append("")

    return "\n".join(lines)
