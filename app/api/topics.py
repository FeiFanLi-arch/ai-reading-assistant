"""
多文章「主题」管理、横向对比总结与跨篇追问 API (Topics REST API)
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.database import session_scope
from app.models import Topic
from app.services.topic_service import (
    TopicServiceError,
    add_article_to_topic,
    ask_topic_followup,
    create_topic,
    export_topic_markdown,
    remove_article_from_topic,
    run_topic_comparison,
    update_topic_articles,
)

topics_bp = Blueprint("topics", __name__)


@topics_bp.get("")
def get_topics():
    """获取所有研究主题列表"""
    with session_scope() as session:
        topics = session.query(Topic).order_by(Topic.updated_at.desc(), Topic.id.desc()).all()
        return jsonify({"items": [t.to_dict(include_details=False) for t in topics]})


@topics_bp.post("")
def post_create_topic():
    """创建新主题，可选关联多篇文章并立即生成横向对比总结"""
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "")
    description = payload.get("description", "")
    color = payload.get("color", "#4f46e5")
    article_ids = payload.get("article_ids") or []
    auto_compare = bool(payload.get("auto_compare", True))

    try:
        with session_scope() as session:
            topic = create_topic(
                session=session,
                name=name,
                description=description,
                color=color,
                article_ids=[int(x) for x in article_ids if str(x).isdigit()],
                auto_compare=auto_compare,
            )
            return jsonify(topic.to_dict(include_details=True)), 201
    except TopicServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@topics_bp.get("/<int:topic_id>")
def get_topic_detail(topic_id: int):
    """获取主题详情（包含收录文章列表、跨文章对比总结报告、跨篇追问历史）"""
    with session_scope() as session:
        topic = session.get(Topic, topic_id)
        if topic is None:
            return jsonify({"error": "未找到该研究主题。"}), 404
        return jsonify(topic.to_dict(include_details=True))


@topics_bp.patch("/<int:topic_id>")
def patch_topic(topic_id: int):
    """更新主题名称、描述、颜色或收录的文章集合"""
    payload = request.get_json(silent=True) or {}
    try:
        with session_scope() as session:
            topic = session.get(Topic, topic_id)
            if topic is None:
                return jsonify({"error": "未找到该研究主题。"}), 404

            if "name" in payload and str(payload["name"]).strip():
                topic.name = str(payload["name"]).strip()[:200]
            if "description" in payload and payload["description"] is not None:
                topic.description = str(payload["description"]).strip()
            if "color" in payload and payload["color"]:
                topic.color = str(payload["color"]).strip()

            if "article_ids" in payload and isinstance(payload["article_ids"], list):
                topic = update_topic_articles(
                    session=session,
                    topic_id=topic_id,
                    article_ids=[int(x) for x in payload["article_ids"] if str(x).isdigit()],
                    auto_compare=bool(payload.get("auto_compare", False)),
                )

            session.flush()
            return jsonify(topic.to_dict(include_details=True))
    except TopicServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@topics_bp.delete("/<int:topic_id>")
def delete_topic(topic_id: int):
    """删除主题（不删除归属其中的文章本身）"""
    with session_scope() as session:
        topic = session.get(Topic, topic_id)
        if topic is None:
            return jsonify({"error": "未找到该研究主题。"}), 404
        session.delete(topic)
        return jsonify({"success": True, "deleted_id": topic_id})


@topics_bp.post("/<int:topic_id>/articles")
def post_add_article_to_topic(topic_id: int):
    """将单篇文章加入该主题"""
    payload = request.get_json(silent=True) or {}
    article_id = payload.get("article_id")
    if not article_id or not str(article_id).isdigit():
        return jsonify({"error": "请提供有效的 article_id。"}), 400

    try:
        with session_scope() as session:
            topic = add_article_to_topic(session, topic_id, int(article_id))
            return jsonify(topic.to_dict(include_details=True))
    except TopicServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@topics_bp.delete("/<int:topic_id>/articles/<int:article_id>")
def delete_remove_article_from_topic(topic_id: int, article_id: int):
    """从主题中移除某篇文章"""
    try:
        with session_scope() as session:
            topic = remove_article_from_topic(session, topic_id, article_id)
            return jsonify(topic.to_dict(include_details=True))
    except TopicServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@topics_bp.post("/<int:topic_id>/compare")
def post_compare_topic(topic_id: int):
    """执行或重新生成该主题下多篇文章的对比总结报告"""
    try:
        with session_scope() as session:
            topic = run_topic_comparison(session, topic_id)
            return jsonify(topic.to_dict(include_details=True))
    except TopicServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@topics_bp.post("/<int:topic_id>/ask")
def post_ask_topic_question(topic_id: int):
    """针对主题下所有文章发起跨篇追问"""
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")

    try:
        with session_scope() as session:
            user_msg, assistant_msg = ask_topic_followup(
                session=session,
                topic_id=topic_id,
                question=question,
            )
            return jsonify(
                {
                    "user_message": user_msg.to_dict(),
                    "assistant_message": assistant_msg.to_dict(),
                }
            )
    except TopicServiceError as exc:
        return jsonify({"error": str(exc)}), 400


@topics_bp.get("/<int:topic_id>/export")
def export_topic(topic_id: int):
    """导出多文章主题对比报告为 Markdown"""
    download = request.args.get("download", "0") in ("1", "true")
    with session_scope() as session:
        topic = session.get(Topic, topic_id)
        if topic is None:
            return jsonify({"error": "未找到该研究主题。"}), 404
        md_content = export_topic_markdown(topic)
        filename = f"topic-synthesis-{topic.id}.md"

        if download:
            return Response(
                md_content,
                mimetype="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        return jsonify({"markdown": md_content, "filename": filename, "title": topic.name})
