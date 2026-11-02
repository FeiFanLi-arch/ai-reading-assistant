"""
数据库连接与会话管理模块 (Database & Session Management)
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# 全局引擎与 Session 工厂（在 init_db 时初始化）
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(database_url: str) -> Engine:
    """
    初始化数据库引擎并自动创建所需的表结构。
    如果是本地 SQLite 文件，自动创建父级目录并开启外键约束。
    """
    global _engine, _SessionLocal

    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        db_file_path = database_url.replace("sqlite:///", "", 1)
        Path(db_file_path).parent.mkdir(parents=True, exist_ok=True)

    connect_args = {}
    engine_kwargs = {"future": True}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool

    _engine = create_engine(
        database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )

    if database_url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    # 导入模型以确保元数据已注册
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=_engine)
    return _engine


def get_session() -> Session:
    """获取一个新的数据库会话实例"""
    if _SessionLocal is None:
        raise RuntimeError("Database has not been initialized. Call init_db() first.")
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """提供事务安全的上下文管理器"""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
