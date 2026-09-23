"""数据库引擎与会话：SQLite WAL + FTS5（trigram）初始化。

FTS5 为外部内容表模式（content='message'），随 message 增删由触发器同步；
trigram 分词要求 SQLite >= 3.34，2 字符以下查询回退 LIKE（trigram 最小 token 为 3 字符）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings

FTS_SQL = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5("
    "content, content='message', content_rowid='id', tokenize='trigram')",
    """
    CREATE TRIGGER IF NOT EXISTS message_fts_insert AFTER INSERT ON message BEGIN
      INSERT INTO message_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    """
    CREATE TRIGGER IF NOT EXISTS message_fts_delete AFTER DELETE ON message BEGIN
      INSERT INTO message_fts(message_fts, rowid, content)
      VALUES ('delete', old.id, old.content);
    END""",
]


def make_engine(settings: Settings):
    if settings.db_url.startswith("sqlite"):
        Path(_sqlite_path(settings.db_url)).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False, "timeout": 30}
        if settings.db_url.startswith("sqlite")
        else {},
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _record):  # noqa: ANN001
        if isinstance(dbapi_conn, sqlite3.Connection):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


def _sqlite_path(db_url: str) -> str:
    prefix = "sqlite:///"
    return db_url[len(prefix) :] if db_url.startswith(prefix) else db_url


def init_db(engine) -> None:
    """建表 + FTS 虚表/触发器（幂等）。生产用 alembic 迁移，此处兜底开发/测试。"""
    from ..models import Base  # 延迟导入避免循环

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for stmt in FTS_SQL:
            conn.execute(text(stmt))


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def fts_supported(engine) -> bool:
    with engine.connect() as conn:
        row = conn.execute(text("select sqlite_version()")).scalar()
        major, minor, _ = (int(x) for x in str(row).split("."))
        return (major, minor) >= (3, 34)


def session_scope(factory) -> Iterator[Session]:
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
