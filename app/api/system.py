"""
系统状态、统计概览与 AI 引擎运行时配置 API (System & Settings API)
"""

from __future__ import annotations

from sqlalchemy import func
from flask import Blueprint, jsonify, request

from app.database import session_scope
from app.models import Article, ArticleMessage, Topic, TopicMessage
from app.services.llm_service import get_runtime_llm_config, save_runtime_llm_config
from app.services.seed_service import seed_initial_data_if_empty

system_bp = Blueprint("system", __name__)


def _mask_api_key(key: str) -> str:
    """对返回给前端展示的 API Key 进行脱敏处理"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


@system_bp.get("/health")
def get_health():
    """容器与服务健康检查接口"""
    with session_scope() as session:
        article_count = session.query(Article).count()
        topic_count = session.query(Topic).count()
        llm_cfg = get_runtime_llm_config(session)
        return jsonify(
            {
                "status": "ok",
                "service": "personal-ai-reading-assistant",
                "active_engine": llm_cfg["active_mode"],
                "article_count": article_count,
                "topic_count": topic_count,
            }
        )


@system_bp.get("/stats")
def get_stats():
    """获取阅读知识库全局统计概览与热门标签"""
    with session_scope() as session:
        total_articles = session.query(Article).count()
        favorite_articles = session.query(Article).filter(Article.is_favorite.is_(True)).count()
        total_topics = session.query(Topic).count()
        total_words = session.query(func.coalesce(func.sum(Article.word_count), 0)).scalar() or 0
        article_qa_count = session.query(ArticleMessage).filter(ArticleMessage.role == "user").count()
        topic_qa_count = session.query(TopicMessage).filter(TopicMessage.role == "user").count()

        # 汇总所有出现过的标签
        all_articles = session.query(Article.tags_json).all()
        tag_freq: dict[str, int] = {}
        import json

        for (tags_raw,) in all_articles:
            try:
                tags_list = json.loads(tags_raw) if tags_raw else []
                for t in tags_list:
                    tag_freq[t] = tag_freq.get(t, 0) + 1
            except Exception:
                continue

        sorted_tags = [
            {"name": k, "count": v}
            for k, v in sorted(tag_freq.items(), key=lambda x: x[1], reverse=True)[:15]
        ]

        llm_cfg = get_runtime_llm_config(session)

        return jsonify(
            {
                "total_articles": total_articles,
                "favorite_articles": favorite_articles,
                "total_topics": total_topics,
                "total_words": int(total_words),
                "total_questions": article_qa_count + topic_qa_count,
                "tags": sorted_tags,
                "active_engine": llm_cfg["active_mode"],
                "llm_model": llm_cfg["model"],
            }
        )


@system_bp.get("/llm-config")
def get_llm_config():
    """读取当前 AI 引擎配置"""
    with session_scope() as session:
        cfg = get_runtime_llm_config(session)
        return jsonify(
            {
                "provider": cfg["provider"],
                "has_api_key": bool(cfg["api_key"]),
                "api_key_masked": _mask_api_key(cfg["api_key"]),
                "base_url": cfg["base_url"],
                "model": cfg["model"],
                "temperature": cfg["temperature"],
                "active_mode": cfg["active_mode"],
            }
        )


@system_bp.put("/llm-config")
def update_llm_config():
    """在 Web 界面动态更新 AI 引擎配置"""
    payload = request.get_json(silent=True) or {}
    with session_scope() as session:
        # 如果前端未传入新 api_key 或传入值为空且不想覆盖已有 key，按 keep_existing_key 标志处理
        if payload.get("keep_existing_key") and not payload.get("api_key"):
            payload.pop("api_key", None)

        cfg = save_runtime_llm_config(session, payload)
        return jsonify(
            {
                "provider": cfg["provider"],
                "has_api_key": bool(cfg["api_key"]),
                "api_key_masked": _mask_api_key(cfg["api_key"]),
                "base_url": cfg["base_url"],
                "model": cfg["model"],
                "temperature": cfg["temperature"],
                "active_mode": cfg["active_mode"],
            }
        )


@system_bp.post("/seed")
def post_seed_demo():
    """一键补充/恢复演示文章与主题"""
    with session_scope() as session:
        result = seed_initial_data_if_empty(session, force=True)
        return jsonify({"success": True, **result})
