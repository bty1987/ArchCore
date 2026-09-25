"""PyWxDump 解密源（主轨真实实现）。

适配 PyWxDump 标准解密输出：MSG0.db ~ MSGn.db 消息分库（跨库合并，svr_id 幂等去重）、
MicroMsg.db Contact 表取群名/联系人备注（尽力而为，失败降级为空名）。

⚠️ M0-02/M0-03 前置：字段映射按 PyWxDump 常见解密库结构编写、尚未在真实环境实测；
首跑如报「解密库结构与预期不符」，按报错的表/字段名修订本文件的 SQL（TD-3，见调研报告第九节）。
未安装 pywxdump 或微信未登录时抛出带指引的运行时错误。
"""

from __future__ import annotations

import glob
import logging
import re
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from .sources import RawMessage, SessionInfo

log = logging.getLogger(__name__)

# PyWxDump 解密库 MSG 表的字段映射草表（以 M0-02 实测为准修订）：
#   StrTalker(会话 wxid), MsgSvrID(全局唯一), Senderwxid, StrContent,
#   CreateTime(unix 秒), Type(类型码), BytesExtra(内含群消息发送者 wxid), IsSender
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

    def _all_dbs(self) -> list[str]:
        return sorted(glob.glob(f"{self.db_dir}/**/*.db", recursive=True))

    def _msg_dbs(self) -> list[str]:
        """消息分库 MSG0.db~MSGn.db；MicroMsg/MediaMSG 按前缀排除。"""
        dbs = [p for p in self._all_dbs() if Path(p).name.upper().startswith("MSG")]
        if not dbs:
            raise RuntimeError(
                f"目录下未找到 MSG 解密库: {self.db_dir}（检查 pywxdump 解密输出路径配置）"
            )
        return dbs

    def _names(self) -> dict[str, str]:
        """MicroMsg.db Contact 表 → {wx_id: 备注/昵称}；失败不阻断消息采集。"""
        names: dict[str, str] = {}
        for p in [p for p in self._all_dbs() if "micromsg" in Path(p).name.lower()]:
            try:
                conn = sqlite3.connect(p)
                conn.row_factory = sqlite3.Row
                for row in conn.execute("SELECT UserName, NickName, Remark FROM Contact"):
                    names[row["UserName"]] = row["Remark"] or row["NickName"] or ""
                conn.close()
            except sqlite3.Error:
                log.warning("读取联系人库失败（%s），会话名以空快照继续", p, exc_info=True)
        return names

    def list_sessions(self) -> list[SessionInfo]:
        names = self._names()
        last_seen: dict[str, int] = {}
        for p in self._msg_dbs():
            conn = sqlite3.connect(p)
            try:
                rows = conn.execute(
                    "SELECT StrTalker, MAX(CreateTime) FROM MSG GROUP BY StrTalker"
                ).fetchall()
            except sqlite3.OperationalError as exc:
                raise RuntimeError(
                    f"解密库结构与预期不符（{p}）：{exc}；请按 TD-3/M0-03 修订 pywxdump_source 字段映射"
                ) from exc
            finally:
                conn.close()
            for wx_id, last_t in rows:
                last_seen[wx_id] = max(last_seen.get(wx_id, 0), last_t or 0)
        return [
            SessionInfo(
                wx_id,
                "group" if wx_id.endswith("@chatroom") else "dm",
                names.get(wx_id, ""),
            )
            for wx_id, _t in sorted(last_seen.items(), key=lambda kv: -kv[1])
        ]

    def iter_messages(
        self, session: SessionInfo, since: datetime | None = None
    ) -> Iterator[RawMessage]:
        for p in self._msg_dbs():
            conn = sqlite3.connect(p)
            conn.row_factory = sqlite3.Row
            try:
                sql = (
                    "SELECT MsgSvrID, Senderwxid, Type, StrContent, CreateTime, "
                    "IsSender, BytesExtra FROM MSG WHERE StrTalker = ?"
                )
                params: list = [session.wx_id]
                if since is not None:
                    sql += " AND CreateTime > ?"
                    params.append(int(since.timestamp()))
                sql += " ORDER BY CreateTime, MsgSvrID"
                for row in conn.execute(sql, params):
                    msg_type = MSG_TYPE_MAP.get(row["Type"], "text")
                    sender = row["Senderwxid"] or _sender_from_bytes_extra(row["BytesExtra"])
                    yield RawMessage(
                        session=session,
                        svr_id=str(row["MsgSvrID"]) if row["MsgSvrID"] else None,
                        sender_wxid=sender,
                        msg_type=msg_type,
                        content=row["StrContent"] or "",
                        ts=datetime.fromtimestamp(row["CreateTime"]),
                        raw={"is_sender": row["IsSender"], "db": Path(p).name},
                    )
            except sqlite3.OperationalError as exc:
                raise RuntimeError(
                    f"解密库结构与预期不符（{p}）：{exc}；请按 TD-3/M0-03 修订 pywxdump_source 字段映射"
                ) from exc
            finally:
                conn.close()


def _sender_from_bytes_extra(blob) -> str | None:
    """群消息发送者在 BytesExtra 二进制内，正则提取 wxid。"""
    if not blob:
        return None
    matches = re.findall(rb"wxid_[0-9a-zA-Z_\-]+", blob)
    return matches[0].decode() if matches else None
