"""PyWxDump 解密源（主轨真实实现）。

⚠️ M0-02/M0-03 前置：字段映射需以《字段映射与质量评估》结论回填
（媒体路径可达性、时间戳口径、群成员可获取性，见调研报告第九节）。
未安装 pywxdump 或微信未登录时抛出带指引的运行时错误。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime

from .sources import RawMessage, SessionInfo

log = logging.getLogger(__name__)

# PyWxDump 解密库表/字段的映射草表（以 M0-02 实测为准修订）：
#   MSG 表:  StrTalker(会话wxid), MsgSvrID, IsSender, Senderwxid/StrContent,
#            CreateTime(unix 秒), Type(消息类型码), BytesExtra(内含群发送者 wxid)
#   群消息发送者在 BytesExtra 的 messages 二进制 XML 中（\x0c 分隔 wxid）
MSG_TYPE_MAP = {1: "text", 3: "image", 34: "voice", 43: "video", 10002: "system"}


class PyWxDumpSource:
    def __init__(self, db_dir: str):
        try:
            import pywxdump  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "未安装 pywxdump：pip install 'archcore-collector[wxdump]'，"
                "并确认微信已在本机登录（M0 验证前提）"
            ) from exc
        self.db_dir = db_dir

    def _connect(self):
        import glob
        import sqlite3

        dbs = glob.glob(f"{self.db_dir}/**/*.db", recursive=True)
        msg_db = next((p for p in dbs if "MSG" in p.upper()), None)
        if msg_db is None:
            raise RuntimeError(f"目录下未找到 MSG 解密库: {self.db_dir}")
        conn = sqlite3.connect(msg_db)
        conn.row_factory = sqlite3.Row
        return conn

    def list_sessions(self) -> list[SessionInfo]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT StrTalker, MAX(CreateTime) AS last_t FROM MSG "
                "GROUP BY StrTalker ORDER BY last_t DESC"
            ).fetchall()
        # 群/单聊区分：群 wxid 以 @chatroom 结尾
        return [
            SessionInfo(
                r["StrTalker"], "group" if r["StrTalker"].endswith("@chatroom") else "dm", ""
            )
            for r in rows
        ]

    def iter_messages(
        self, session: SessionInfo, since: datetime | None = None
    ) -> Iterator[RawMessage]:

        with self._connect() as conn:
            sql = (
                "SELECT MsgSvrID, Senderwxid, Type, StrContent, CreateTime, IsSender "
                "FROM MSG WHERE StrTalker = ?"
            )
            params: list = [session.wx_id]
            if since is not None:
                sql += " AND CreateTime > ?"
                params.append(int(since.timestamp()))
            sql += " ORDER BY CreateTime, MsgSvrID"
            for row in conn.execute(sql, params).fetchall():
                msg_type = MSG_TYPE_MAP.get(row["Type"], "text")
                sender = row["Senderwxid"]
                if session.type == "group" and not sender:
                    sender = _sender_from_bytes_extra(row, "BytesExtra")
                yield RawMessage(
                    session=session,
                    svr_id=str(row["MsgSvrID"]) if row["MsgSvrID"] else None,
                    sender_wxid=sender,
                    msg_type=msg_type,
                    content=row["StrContent"] or "",
                    ts=datetime.fromtimestamp(row["CreateTime"]),
                    raw={"is_sender": row["IsSender"]},
                )


def _sender_from_bytes_extra(row, col: str) -> str | None:
    import re

    blob = row.get(col, None)
    if not blob:
        return None
    matches = re.findall(rb"wxid_[0-9a-zA-Z_\-]+", blob)
    return matches[0].decode() if matches else None
