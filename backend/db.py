"""Small, explicit SQLite persistence layer; one connection per operation."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import settings

SCHEMA_VERSION = 1


@contextmanager
def connect():
    connection = sqlite3.connect(settings.db_path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("数据库版本高于应用版本，请升级应用")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS topics (
          id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
          description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS articles (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT, text TEXT NOT NULL,
          topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
          favorite INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, word_count INTEGER NOT NULL,
          summary TEXT, mode TEXT NOT NULL, error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(topic_id);
        CREATE INDEX IF NOT EXISTS idx_articles_updated ON articles(updated_at DESC);
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
          role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
          created_at TEXT NOT NULL, mode TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_article ON messages(article_id, created_at);
        CREATE TABLE IF NOT EXISTS comparisons (
          id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
          article_ids TEXT NOT NULL, created_at TEXT NOT NULL, mode TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_comparisons_topic ON comparisons(topic_id, created_at DESC);
        PRAGMA user_version=1;
        """)


def article_dict(row) -> dict:
    value = dict(row)
    value["favorite"] = bool(value["favorite"])
    value["summary"] = json.loads(value["summary"]) if value["summary"] else None
    return value


def comparison_dict(row) -> dict:
    value = dict(row)
    value["article_ids"] = json.loads(value["article_ids"])
    value["result"] = json.loads(value["result"])
    return value


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False)
