"""本地状态：水位（每会话已同步到的最后 ts）+ 发件箱（断点续传队列）。

本地 SQLite，独立于 server 库；上报失败的数据留在 outbox，按指数退避重试。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watermark (
  wx_id TEXT PRIMARY KEY,
  last_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payload TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS ix_outbox_pending ON outbox(status, next_attempt_at);
"""


class StateStore:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # ---- 水位 ----

    def get_watermark(self, wx_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT last_ts FROM watermark WHERE wx_id = ?", (wx_id,)
        ).fetchone()
        return row[0] if row else None

    def set_watermark(self, wx_id: str, ts_iso: str) -> None:
        self.conn.execute(
            "INSERT INTO watermark(wx_id, last_ts) VALUES(?, ?) "
            "ON CONFLICT(wx_id) DO UPDATE SET last_ts = excluded.last_ts",
            (wx_id, ts_iso),
        )
        self.conn.commit()

    # ---- 发件箱 ----

    def enqueue(self, payload: str) -> int:
        cur = self.conn.execute("INSERT INTO outbox(payload) VALUES(?)", (payload,))
        self.conn.commit()
        return cur.lastrowid

    def take_pending(self, limit: int) -> list[tuple[int, str]]:
        now = time.time()
        return self.conn.execute(
            "SELECT id, payload FROM outbox WHERE status = 'pending' "
            "AND next_attempt_at <= ? ORDER BY id LIMIT ?",
            (now, limit),
        ).fetchall()

    def mark_sent(self, ids: list[int]) -> None:
        self.conn.executemany(
            "UPDATE outbox SET status = 'sent' WHERE id = ?",
            [(i,) for i in ids],
        )
        self.conn.commit()

    def mark_retry(self, ids: list[int], attempts_by_id: dict[int, int]) -> None:
        now = time.time()
        rows = []
        for i in ids:
            attempts = attempts_by_id.get(i, 1)
            backoff = min(600, 2 ** min(attempts, 6))  # 指数退避，上限 10 分钟
            rows.append((attempts, now + backoff, i))
        self.conn.executemany(
            "UPDATE outbox SET attempts = ?, next_attempt_at = ? WHERE id = ?", rows
        )
        self.conn.commit()

    def pending_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM outbox WHERE status = 'pending'").fetchone()[
            0
        ]

    def close(self) -> None:
        self.conn.close()
