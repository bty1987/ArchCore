"""alembic 迁移验证：upgrade head 后 schema 与模型一致、FTS 虚表存在。"""

import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR / "src"))


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("ARCHCORE_DB_URL", f"sqlite:///{db_path.as_posix()}")
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    command.upgrade(cfg, "head")
    return db_path


def test_upgrade_head_creates_all_tables(migrated_db):
    import sqlite3

    conn = sqlite3.connect(str(migrated_db))
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()
    expected = {
        "app_user",
        "customer",
        "chat_session",
        "contact",
        "member",
        "group_member_snap",
        "message",
        "message_daily",
        "alert_rule",
        "alert",
        "notify_channel",
        "notify_record",
        "inapp_notification",
        "keyword",
        "sync_task",
        "audit_log",
        "app_setting",
        "message_fts",
        "alembic_version",
    }
    missing = expected - tables
    assert not missing, f"迁移缺表: {missing}"


def test_fts_search_works_after_migration(migrated_db):
    import sqlite3

    conn = sqlite3.connect(str(migrated_db))
    conn.execute(
        "INSERT INTO chat_session(id, wx_id, type, name, status, created_at) "
        "VALUES(1, 'g@chatroom', 'group', '群', 'active', datetime('now'))"
    )
    conn.execute(
        "INSERT INTO message"
        "(id, session_id, sender_type, msg_type, content, ts, recalled, source, created_at) "
        "VALUES(1, 1, 'external', 'text', '合同条款已经发出',"
        " datetime('now'), 0, 'decrypt', datetime('now'))"
    )
    hits = conn.execute(
        "SELECT rowid FROM message_fts WHERE message_fts MATCH '\"合同条款\"'"
    ).fetchall()
    conn.close()
    assert len(hits) == 1


def test_upgrade_is_idempotent(migrated_db, monkeypatch):
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    command.upgrade(cfg, "head")  # 已是 head，不应报错
    assert True
