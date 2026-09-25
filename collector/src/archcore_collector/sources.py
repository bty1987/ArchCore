"""解密源适配层（TD-3）：统一接口隔离 PyWxDump / WeChatDataAnalysis / fixture。

真实解密源在 M0-02/M0-06 验证后完善字段映射；当前 fixture 源用于开发与端到端测试。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class SessionInfo:
    wx_id: str
    type: str  # group / dm
    name: str


@dataclass
class RawMessage:
    """与微信解密库行对应的原始结构（标准化前的形态）。"""

    session: SessionInfo
    svr_id: str | None
    sender_wxid: str | None
    msg_type: str
    content: str
    ts: datetime
    recalled: bool = False
    media_meta: dict | None = None
    raw: dict | None = None


class DecryptSource(Protocol):
    def list_sessions(self) -> list[SessionInfo]: ...

    def iter_messages(
        self, session: SessionInfo, since: datetime | None = None
    ) -> Iterator[RawMessage]: ...


class FixtureSource:
    """读取 gen-fixtures 生成的样本库（脱敏合成数据，开发/测试/演示专用）。"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_sessions(self) -> list[SessionInfo]:
        with self._conn() as conn:
            rows = conn.execute("SELECT wx_id, type, name FROM session ORDER BY wx_id").fetchall()
        return [SessionInfo(r["wx_id"], r["type"], r["name"]) for r in rows]

    def iter_messages(
        self, session: SessionInfo, since: datetime | None = None
    ) -> Iterator[RawMessage]:
        conn = self._conn()
        try:
            sql = (
                "SELECT svr_id, sender_wxid, msg_type, content, ts, recalled, media_meta "
                "FROM msg WHERE session_wx_id = ?"
            )
            params: list = [session.wx_id]
            if since is not None:
                sql += " AND ts > ?"
                params.append(since.isoformat(sep=" ", timespec="seconds"))
            sql += " ORDER BY ts, svr_id"
            for row in conn.execute(sql, params).fetchall():
                meta = None
                if row["media_meta"]:
                    import json

                    meta = json.loads(row["media_meta"])
                yield RawMessage(
                    session=session,
                    svr_id=row["svr_id"],
                    sender_wxid=row["sender_wxid"],
                    msg_type=row["msg_type"],
                    content=row["content"] or "",
                    ts=datetime.fromisoformat(row["ts"]),
                    recalled=bool(row["recalled"]),
                    media_meta=meta,
                    raw={"fixture": True},
                )
        finally:
            conn.close()


def build_source(cfg) -> DecryptSource:
    if cfg.type == "fixture":
        return FixtureSource(cfg.fixture_path)
    if cfg.type == "pywxdump":
        from .pywxdump_source import PyWxDumpSource  # 3.x 路线（登录窗口受限）

        return PyWxDumpSource(cfg.db_dir)
    if cfg.type == "wechat4":
        from .wechat4_source import WeChat4Source  # 4.x 降级路线主轨（M0-06 已验证）

        return WeChat4Source(cfg.db_dir)
    raise ValueError(f"未知数据源类型: {cfg.type}")
