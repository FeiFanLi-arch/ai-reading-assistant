"""FastAPI routes and application composition.

Run from project root: uvicorn backend.main:app --host 127.0.0.1 --port 8000
All API persistence is server-side SQLite. Sync endpoints run in FastAPI's
threadpool, keeping blocking SQLite/network work off the event loop.
"""

import hmac
import logging
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ai, db
from .config import ROOT, settings
from .extraction import ExtractionError, fetch_article, normalize_text
from .schemas import ArticleInput, ArticlePatch, Backup, CompareInput, QuestionInput, TopicInput

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 20_000_000


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid.uuid4())


@asynccontextmanager
async def lifespan(_app):
    if settings.ai_mode not in {"auto", "demo", "ai"}:
        raise RuntimeError("AI_MODE 必须是 auto、demo 或 ai")
    if not settings.base_url.startswith(("https://", "http://")):
        raise RuntimeError("AI_BASE_URL 必须是 http(s) URL")
    db.initialize()
    yield


app = FastAPI(title="个人 AI 阅读助手", version="1.0.0", lifespan=lifespan)


class BodyLimitMiddleware:
    """Reject oversized/chunked requests before JSON decoding allocates memory."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        parts, length = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            length += len(body)
            if length > MAX_BODY_BYTES:
                return await JSONResponse({"detail": "请求过大，最多允许 20 MB"}, status_code=413)(scope, receive, send)
            parts.append(body)
            if not message.get("more_body", False):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(parts), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BodyLimitMiddleware)


@app.middleware("http")
async def protect_and_headers(request: Request, call_next):
    protected = request.url.path.startswith("/api/") or request.url.path in {"/docs", "/openapi.json", "/redoc"}
    if protected and settings.access_token:
        token = request.headers.get("x-access-token", "")
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        if not hmac.compare_digest(token.encode(), settings.access_token.encode()):
            return JSONResponse({"detail": "请输入正确的访问令牌"}, status_code=401)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "不允许跨站写入请求"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc):
    parts = []
    for error in exc.errors()[:5]:
        location = ".".join(str(part) for part in error["loc"] if part != "body")
        parts.append(f"{location}: {error['msg']}" if location else error["msg"])
    return JSONResponse({"detail": "；".join(parts)}, status_code=422)


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(_request, _exc):
    return JSONResponse({"detail": "记录冲突，请检查主题名称是否重复，或关联记录是否存在"}, status_code=409)


@app.exception_handler(ai.AIError)
async def ai_error(_request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=502)


def require_topic(connection, topic_id: str):
    row = connection.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "主题不存在")
    return dict(row)


def require_article(connection, article_id: str) -> dict:
    row = connection.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")
    return db.article_dict(row)


def topic_with_count(connection, topic_id: str) -> dict:
    topic = require_topic(connection, topic_id)
    topic["article_count"] = connection.execute("SELECT COUNT(*) FROM articles WHERE topic_id=?", (topic_id,)).fetchone()[0]
    return topic


@app.get("/health")
def health():
    with db.connect() as connection:
        connection.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.get("/api/config")
def configuration():
    return {"mode": settings.mode, "model": settings.model if settings.mode == "ai" else "本地规则摘录", "max_text_length": settings.max_text_length}


@app.get("/api/topics")
def list_topics():
    with db.connect() as connection:
        return [dict(row) for row in connection.execute("""SELECT topics.*, COUNT(articles.id) AS article_count
             FROM topics LEFT JOIN articles ON articles.topic_id=topics.id GROUP BY topics.id
             ORDER BY topics.created_at DESC""").fetchall()]


@app.post("/api/topics", status_code=201)
def create_topic(data: TopicInput):
    topic_id = new_id()
    with db.connect() as connection:
        connection.execute("INSERT INTO topics(id,name,description,created_at) VALUES(?,?,?,?)", (topic_id, data.name, data.description, now()))
        return topic_with_count(connection, topic_id)


@app.patch("/api/topics/{topic_id}")
def update_topic(topic_id: str, data: TopicInput):
    with db.connect() as connection:
        require_topic(connection, topic_id)
        connection.execute("UPDATE topics SET name=?,description=? WHERE id=?", (data.name, data.description, topic_id))
        return topic_with_count(connection, topic_id)


@app.delete("/api/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: str):
    with db.connect() as connection:
        require_topic(connection, topic_id)
        connection.execute("DELETE FROM topics WHERE id=?", (topic_id,))
    return Response(status_code=204)


@app.get("/api/articles")
def list_articles(q: str = Query(default="", max_length=300), topic_id: str | None = None,
                  favorite: bool | None = None, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    predicates, parameters = [], []
    if q:
        predicates.append("(title LIKE ? ESCAPE '\\' OR text LIKE ? ESCAPE '\\')")
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        parameters.extend([f"%{escaped}%", f"%{escaped}%"])
    if topic_id:
        predicates.append("topic_id=?")
        parameters.append(topic_id)
    if favorite is not None:
        predicates.append("favorite=?")
        parameters.append(int(favorite))
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    with db.connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM articles" + where, parameters).fetchone()[0]
        rows = connection.execute("SELECT * FROM articles" + where + " ORDER BY updated_at DESC, rowid DESC LIMIT ? OFFSET ?", [*parameters, limit, offset]).fetchall()
    return {"items": [db.article_dict(row) for row in rows], "total": total}


def perform_summary(article_id: str):
    with db.connect() as connection:
        article = require_article(connection, article_id)
    try:
        summary = ai.summarize(article["text"], article["title"])
        error = None
    except ai.AIError as exc:
        summary = article["summary"]
        error = str(exc)
    with db.connect() as connection:
        require_article(connection, article_id)
        # Retain the prior successful summary's provenance on failed regeneration.
        mode = article["mode"] if error and summary else settings.mode
        connection.execute("UPDATE articles SET summary=?,mode=?,error=?,updated_at=? WHERE id=?",
                           (db.encode(summary) if summary else None, mode, error, now(), article_id))
        return require_article(connection, article_id)


@app.post("/api/articles", status_code=201)
def create_article(data: ArticleInput):
    if data.topic_id:
        with db.connect() as connection:
            require_topic(connection, data.topic_id)
    if data.url:
        try:
            extracted_title, text = fetch_article(data.url)
        except ExtractionError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        text = normalize_text(data.text or "")
        if not 20 <= len(text) <= settings.max_text_length:
            raise HTTPException(422, "清理空白与无效字符后的正文需要 20 至 100000 个字符")
        extracted_title = text.splitlines()[0][:100]
    article_id, timestamp = new_id(), now()
    title = (data.title or "").strip() or extracted_title or "未命名文章"
    # Chinese characters and Latin words form an approximate reading-length count.
    word_count = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text))
    with db.connect() as connection:
        connection.execute("""INSERT INTO articles(id,title,url,text,topic_id,created_at,updated_at,word_count,mode)
             VALUES(?,?,?,?,?,?,?,?,?)""", (article_id, title, data.url, text, data.topic_id or None, timestamp, timestamp, word_count, settings.mode))
    return perform_summary(article_id)


@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    with db.connect() as connection:
        return require_article(connection, article_id)


@app.patch("/api/articles/{article_id}")
def update_article(article_id: str, data: ArticlePatch):
    updates = data.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is None:
        raise HTTPException(422, "标题不能为空")
    if "favorite" in updates and updates["favorite"] is None:
        raise HTTPException(422, "收藏状态不能为空")
    with db.connect() as connection:
        require_article(connection, article_id)
        if updates.get("topic_id"):
            require_topic(connection, updates["topic_id"])
        if "topic_id" in updates:
            updates["topic_id"] = updates["topic_id"] or None
        if updates:
            # Keys come exclusively from the Pydantic model above.
            assignments = ",".join(key + "=?" for key in updates)
            connection.execute(f"UPDATE articles SET {assignments},updated_at=? WHERE id=?", [*updates.values(), now(), article_id])
        return require_article(connection, article_id)


@app.delete("/api/articles/{article_id}", status_code=204)
def delete_article(article_id: str):
    with db.connect() as connection:
        require_article(connection, article_id)
        for row in connection.execute("SELECT id,article_ids FROM comparisons").fetchall():
            import json
            if article_id in json.loads(row["article_ids"]):
                connection.execute("DELETE FROM comparisons WHERE id=?", (row["id"],))
        connection.execute("DELETE FROM articles WHERE id=?", (article_id,))
    return Response(status_code=204)


@app.post("/api/articles/{article_id}/summarize")
def regenerate_summary(article_id: str):
    return perform_summary(article_id)


@app.get("/api/articles/{article_id}/messages")
def list_messages(article_id: str):
    with db.connect() as connection:
        require_article(connection, article_id)
        return [dict(row) for row in connection.execute("SELECT * FROM messages WHERE article_id=? ORDER BY created_at,rowid", (article_id,)).fetchall()]


@app.post("/api/articles/{article_id}/messages", status_code=201)
def ask_question(article_id: str, data: QuestionInput):
    with db.connect() as connection:
        article = require_article(connection, article_id)
        history = [dict(row) for row in connection.execute("SELECT * FROM messages WHERE article_id=? ORDER BY created_at DESC,rowid DESC LIMIT 12", (article_id,)).fetchall()][::-1]
    answer = ai.answer(article["text"], article["title"], data.question, history)
    user = {"id": new_id(), "article_id": article_id, "role": "user", "content": data.question, "created_at": now(), "mode": settings.mode}
    assistant = {"id": new_id(), "article_id": article_id, "role": "assistant", "content": answer, "created_at": now(), "mode": settings.mode}
    with db.connect() as connection:
        require_article(connection, article_id)
        for message in (user, assistant):
            connection.execute("INSERT INTO messages(id,article_id,role,content,created_at,mode) VALUES(?,?,?,?,?,?)", tuple(message.values()))
        connection.execute("UPDATE articles SET updated_at=? WHERE id=?", (now(), article_id))
    return {"user": user, "assistant": assistant}


@app.post("/api/topics/{topic_id}/compare", status_code=201)
def compare_articles(topic_id: str, data: CompareInput):
    with db.connect() as connection:
        require_topic(connection, topic_id)
        rows = connection.execute("SELECT * FROM articles WHERE topic_id=? ORDER BY created_at", (topic_id,)).fetchall()
        articles = [db.article_dict(row) for row in rows]
    if data.article_ids is not None:
        requested = set(data.article_ids)
        if len(requested) != len(data.article_ids):
            raise HTTPException(422, "请选择不同的文章")
        articles = [article for article in articles if article["id"] in requested]
        if len(articles) != len(requested):
            raise HTTPException(422, "所有对比文章必须存在且属于当前主题")
    if not 2 <= len(articles) <= 10:
        raise HTTPException(422, "每次请选择 2 至 10 篇同主题文章进行对比")
    result = ai.compare(articles)
    comparison = {"id": new_id(), "topic_id": topic_id, "article_ids": [article["id"] for article in articles], "created_at": now(), "mode": settings.mode, "result": result}
    with db.connect() as connection:
        require_topic(connection, topic_id)
        for article in articles:
            current = require_article(connection, article["id"])
            if current["topic_id"] != topic_id:
                raise HTTPException(409, "文章主题已改变，请重新选择后对比")
        connection.execute("INSERT INTO comparisons(id,topic_id,article_ids,created_at,mode,result) VALUES(?,?,?,?,?,?)", (comparison["id"], topic_id, db.encode(comparison["article_ids"]), comparison["created_at"], settings.mode, db.encode(result)))
    return comparison


@app.get("/api/topics/{topic_id}/comparisons")
def list_comparisons(topic_id: str):
    with db.connect() as connection:
        require_topic(connection, topic_id)
        return [db.comparison_dict(row) for row in connection.execute("SELECT * FROM comparisons WHERE topic_id=? ORDER BY created_at DESC,rowid DESC", (topic_id,)).fetchall()]


@app.get("/api/export")
def export_backup():
    with db.connect() as connection:
        # Explicit read transaction guarantees all tables belong to one snapshot.
        connection.execute("BEGIN")
        return {"version": 1, "exported_at": now(),
                "topics": [dict(row) for row in connection.execute("SELECT * FROM topics").fetchall()],
                "articles": [db.article_dict(row) for row in connection.execute("SELECT * FROM articles").fetchall()],
                "messages": [dict(row) for row in connection.execute("SELECT * FROM messages ORDER BY created_at,rowid").fetchall()],
                "comparisons": [db.comparison_dict(row) for row in connection.execute("SELECT * FROM comparisons").fetchall()]}


@app.post("/api/import")
def import_backup(data: Backup):
    imported = {"topics": 0, "articles": 0, "messages": 0, "comparisons": 0}
    skipped = 0
    with db.connect() as connection:
        # A single immediate transaction makes merge/validation atomic.
        connection.execute("BEGIN IMMEDIATE")
        existing = {table: {row[0] for row in connection.execute(f"SELECT id FROM {table}").fetchall()} for table in imported}
        for table in imported:
            ids = [item.id for item in getattr(data, table)]
            if len(ids) != len(set(ids)):
                raise HTTPException(422, f"备份中 {table} 存在重复 ID")
        topics = existing["topics"] | {item.id for item in data.topics}
        articles = existing["articles"] | {item.id for item in data.articles}
        for item in data.articles:
            if item.topic_id and item.topic_id not in topics:
                raise HTTPException(422, "备份文章引用了不存在的主题")
        for item in data.messages:
            if item.article_id not in articles:
                raise HTTPException(422, "备份对话引用了不存在的文章")
        for item in data.comparisons:
            if item.topic_id not in topics or any(identifier not in articles for identifier in item.article_ids):
                raise HTTPException(422, "备份对比引用了不存在的主题或文章")
        for table in imported:
            for item in getattr(data, table):
                if item.id in existing[table]:
                    skipped += 1
                    continue
                record = item.model_dump()
                record.pop("article_count", None)
                for key in ("summary", "result", "article_ids"):
                    if key in record and record[key] is not None:
                        record[key] = db.encode(record[key])
                if "favorite" in record:
                    record["favorite"] = int(record["favorite"])
                columns = ",".join(record)
                marks = ",".join("?" for _ in record)
                connection.execute(f"INSERT INTO {table}({columns}) VALUES({marks})", tuple(record.values()))
                imported[table] += 1
    return {"imported": imported, "skipped": skipped}


FRONTEND = ROOT / "frontend"
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/", include_in_schema=False)
def frontend():
    index = FRONTEND / "index.html"
    if not index.exists():
        raise HTTPException(503, "前端资源不存在，请确认项目 frontend 目录完整")
    return FileResponse(index)
