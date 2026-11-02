"""
文章管理、结构化摘要、追问对话与导出 API (Articles REST API)
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.database import session_scope
from app.models import Article, ArticleMessage
from app.services.article_service import (
    ArticleServiceError,
    ask_followup_question,
    create_article,
    export_article_markdown,
    list_articles,
    regenerate_summary,
)
from app.services.seed_service import SAMPLE_ARTICLES

articles_bp = Blueprint("articles", __name__)


@articles_bp.get("")
def get_articles():
    """查询历史阅读文章列表，支持搜索、标签、主题、收藏与阅读状态筛选"""
    search = request.args.get("search")
    tag = request.args.get("tag")
    topic_id_raw = request.args.get("topic_id")
    favorite_raw = request.args.get("favorite", "false").lower()
    status = request.args.get("status")

    topic_id = int(topic_id_raw) if topic_id_raw and topic_id_raw.isdigit() else None
    favorite_only = favorite_raw in ("1", "true", "yes")

    with session_scope() as session:
        items = list_articles(
            session=session,
            search=search,
            tag=tag,
            topic_id=topic_id,
            favorite_only=favorite_only,
            reading_status=status,
        )
        return jsonify({"items": items, "total": len(items)})


@articles_bp.get("/samples")
def get_sample_articles():
    """获取内置示例文章模板，方便前端一键填入体验"""
    return jsonify({"samples": SAMPLE_ARTICLES})


@articles_bp.post("")
def post_create_article():
    """新增文章（通过 URL 抓取或直接粘贴文本）并生成结构化摘要"""
    payload = request.get_json(silent=True) or {}
    source_type = payload.get("source_type", "text")
    url = payload.get("url")
    raw_text = payload.get("raw_text")
    title = payload.get("title")
    author = payload.get("author")
    topic_ids = payload.get("topic_ids") or []

    try:
        with session_scope() as session:
            article = create_article(
                session=session,
                source_type=source_type,
                url=url,
                raw_text=raw_text,
                title=title,
                author=author,
                topic_ids=[int(x) for x in topic_ids if str(x).isdigit()],
            )
            return jsonify(article.to_dict(include_details=True)), 201
    except ArticleServiceError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"创建文章失败：{exc}"}), 500


@articles_bp.get("/<int:article_id>")
def get_article_detail(article_id: int):
    """获取单篇文章完整详情（含原文、结构化摘要、追问对话记录、个人笔记）"""
    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            return jsonify({"error": "未找到该文章记录。"}), 404
        return jsonify(article.to_dict(include_details=True))


@articles_bp.patch("/<int:article_id>")
def patch_article(article_id: int):
    """更新文章属性（标题、个人批注笔记、收藏状态、阅读进度状态、标签）"""
    payload = request.get_json(silent=True) or {}
    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            return jsonify({"error": "未找到该文章记录。"}), 404

        if "title" in payload and payload["title"]:
            article.title = str(payload["title"]).strip()[:300]
        if "user_notes" in payload and payload["user_notes"] is not None:
            article.user_notes = str(payload["user_notes"])
        if "is_favorite" in payload:
            article.is_favorite = bool(payload["is_favorite"])
        if "reading_status" in payload and payload["reading_status"] in ("unread", "reading", "completed"):
            article.reading_status = payload["reading_status"]
        if "tags" in payload and isinstance(payload["tags"], list):
            article.tags = [str(t).strip() for t in payload["tags"] if str(t).strip()]

        session.flush()
        return jsonify(article.to_dict(include_details=True))


@articles_bp.delete("/<int:article_id>")
def delete_article(article_id: int):
    """删除单篇文章历史记录"""
    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            return jsonify({"error": "未找到该文章记录。"}), 404
        session.delete(article)
        return jsonify({"success": True, "deleted_id": article_id})


@articles_bp.post("/<int:article_id>/regenerate")
def post_regenerate_summary(article_id: int):
    """重新生成文章的结构化摘要"""
    try:
        with session_scope() as session:
            article = regenerate_summary(session, article_id)
            return jsonify(article.to_dict(include_details=True))
    except ArticleServiceError as exc:
        return jsonify({"error": str(exc)}), 404


@articles_bp.post("/<int:article_id>/ask")
def post_ask_question(article_id: int):
    """对文章发起追问（支持附带引用原文或观点片段）"""
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")
    quoted_text = payload.get("quoted_text")

    try:
        with session_scope() as session:
            user_msg, assistant_msg = ask_followup_question(
                session=session,
                article_id=article_id,
                question=question,
                quoted_text=quoted_text,
            )
            return jsonify(
                {
                    "user_message": user_msg.to_dict(),
                    "assistant_message": assistant_msg.to_dict(),
                }
            )
    except ArticleServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@articles_bp.delete("/<int:article_id>/messages")
def delete_article_messages(article_id: int):
    """清空指定文章的追问历史对话"""
    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            return jsonify({"error": "未找到该文章记录。"}), 404
        session.query(ArticleMessage).filter(ArticleMessage.article_id == article_id).delete()
        return jsonify({"success": True})


@articles_bp.get("/<int:article_id>/export")
def export_article(article_id: int):
    """导出文章结构化读书笔记为 Markdown"""
    download = request.args.get("download", "0") in ("1", "true")
    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            return jsonify({"error": "未找到该文章记录。"}), 404
        md_content = export_article_markdown(article)
        filename = f"reading-note-{article.id}.md"

        if download:
            return Response(
                md_content,
                mimetype="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        return jsonify({"markdown": md_content, "filename": filename, "title": article.title})
