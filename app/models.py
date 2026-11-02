"""
领域数据模型模块 (Domain Models)

包含：
- Article: 单篇阅读文章及其结构化摘要、个人批注、标签、阅读状态
- ArticleMessage: 针对单篇文章的追问对话历史（支持引用原文或观点片段）
- Topic: 多文章聚合对比「主题」及其对比综述报告
- TopicArticle: 主题与文章的多对多关联实体
- TopicMessage: 针对整个主题下所有文章的跨篇追问对话历史
- AppSetting: 系统级配置键值存储（如运行时 AI 模型参数）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """获取当前 UTC 时间"""
    return datetime.now(timezone.utc)


def format_iso(dt: datetime | None) -> str | None:
    """将 datetime 格式化为 ISO 8601 字符串"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class Article(Base):
    """文章与结构化阅读卡片实体"""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)  # url | text | file
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    site_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reading_time_minutes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # 结构化摘要 JSON 字符串
    summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # 标签列表 JSON 字符串
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    # 用户个人批注与笔记
    user_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reading_status: Mapped[str] = mapped_column(String(32), default="unread", nullable=False)  # unread | reading | completed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # 关联关系
    messages: Mapped[list[ArticleMessage]] = relationship(
        "ArticleMessage",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="ArticleMessage.created_at.asc()",
    )
    topic_links: Mapped[list[TopicArticle]] = relationship(
        "TopicArticle",
        back_populates="article",
        cascade="all, delete-orphan",
    )

    @property
    def summary(self) -> dict[str, Any]:
        try:
            data = json.loads(self.summary_json) if self.summary_json else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @summary.setter
    def summary(self, value: dict[str, Any]) -> None:
        self.summary_json = json.dumps(value, ensure_ascii=False)

    @property
    def tags(self) -> list[str]:
        try:
            data = json.loads(self.tags_json) if self.tags_json else []
            return [str(x) for x in data] if isinstance(data, list) else []
        except Exception:
            return []

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self.tags_json = json.dumps(list(dict.fromkeys(value)), ensure_ascii=False)

    def to_dict(self, include_details: bool = True) -> dict[str, Any]:
        """序列化为字典格式供 API 返回"""
        summary_data = self.summary
        topic_items = [
            {
                "id": link.topic.id,
                "name": link.topic.name,
                "color": link.topic.color,
            }
            for link in self.topic_links
            if link.topic is not None
        ]
        result: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "site_name": self.site_name,
            "author": self.author,
            "word_count": self.word_count,
            "reading_time_minutes": self.reading_time_minutes,
            "one_sentence_summary": summary_data.get("one_sentence_summary", ""),
            "tags": self.tags,
            "is_favorite": self.is_favorite,
            "reading_status": self.reading_status,
            "topics": topic_items,
            "message_count": len(self.messages) if self.messages is not None else 0,
            "engine_used": summary_data.get("engine_used", "heuristic"),
            "created_at": format_iso(self.created_at),
            "updated_at": format_iso(self.updated_at),
        }
        if include_details:
            result["raw_content"] = self.raw_content
            result["summary"] = summary_data
            result["user_notes"] = self.user_notes
            result["messages"] = [m.to_dict() for m in self.messages]
        else:
            # 列表摘要预览视图，提供前 160 字正文预览和核心观点数
            result["content_preview"] = (self.raw_content or "")[:160].strip()
            result["core_viewpoint_count"] = len(summary_data.get("core_viewpoints", []))
        return result


class ArticleMessage(Base):
    """单篇文章追问对话记录实体"""

    __tablename__ = "article_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_used: Mapped[str] = mapped_column(String(32), default="heuristic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    article: Mapped[Article] = relationship("Article", back_populates="messages")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "article_id": self.article_id,
            "role": self.role,
            "content": self.content,
            "quoted_text": self.quoted_text,
            "engine_used": self.engine_used,
            "created_at": format_iso(self.created_at),
        }


class Topic(Base):
    """多文章研究「主题」实体"""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    color: Mapped[str] = mapped_column(String(32), default="#4f46e5", nullable=False)
    comparison_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    article_links: Mapped[list[TopicArticle]] = relationship(
        "TopicArticle",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="TopicArticle.added_at.asc()",
    )
    messages: Mapped[list[TopicMessage]] = relationship(
        "TopicMessage",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="TopicMessage.created_at.asc()",
    )

    @property
    def comparison(self) -> dict[str, Any]:
        try:
            data = json.loads(self.comparison_json) if self.comparison_json else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @comparison.setter
    def comparison(self, value: dict[str, Any]) -> None:
        self.comparison_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self, include_details: bool = True) -> dict[str, Any]:
        articles_list = [
            link.article.to_dict(include_details=False)
            for link in self.article_links
            if link.article is not None
        ]
        comp_data = self.comparison
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "article_count": len(articles_list),
            "has_comparison": bool(comp_data and comp_data.get("overview")),
            "created_at": format_iso(self.created_at),
            "updated_at": format_iso(self.updated_at),
        }
        if include_details:
            result["articles"] = articles_list
            result["comparison"] = comp_data
            result["messages"] = [m.to_dict() for m in self.messages]
        else:
            result["article_ids"] = [a["id"] for a in articles_list]
        return result


class TopicArticle(Base):
    """主题与文章的多对多关联关系表"""

    __tablename__ = "topic_articles"
    __table_args__ = (
        UniqueConstraint("topic_id", "article_id", name="uq_topic_article"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    topic: Mapped[Topic] = relationship("Topic", back_populates="article_links")
    article: Mapped[Article] = relationship("Article", back_populates="topic_links")


class TopicMessage(Base):
    """跨多篇文章的主题级追问对话记录实体"""

    __tablename__ = "topic_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    engine_used: Mapped[str] = mapped_column(String(32), default="heuristic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    topic: Mapped[Topic] = relationship("Topic", back_populates="messages")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "role": self.role,
            "content": self.content,
            "engine_used": self.engine_used,
            "created_at": format_iso(self.created_at),
        }


class AppSetting(Base):
    """系统设置持久化表（用于保存 Web UI 动态调整的 LLM 配置等）"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
