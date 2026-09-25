"""微信 4.x 解密库数据源（降级路线主轨，M0-06 验证通过）。

前置：先运行 scripts/decrypt_wechat4.py 生成明文库（data/wechat4_plain/<账号>），
本源读取明文 SQLite，不再接触加密库与进程内存。

已实测的 4.1.15 结构（2026-09，详见 _summary.json 与 docs/local-deploy-guide）：
- message/message_*.db：每个会话一张 `Msg_<md5(talker)>` 表 + 库级 `Name2Id`（username→id）；
  字段 server_id(原生消息ID)、real_sender_id(→Name2Id)、create_time(unix 秒)、
  local_type(低 32 位=类型，高 32 位=子类型)、message_content；WCDB_CT_*=4 表示 ZSTD 压缩；
- contact/contact.db：contact（username/nick_name/remark）、chat_room（群）、chatroom_member。
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from .sources import RawMessage, SessionInfo

log = logging.getLogger(__name__)

TYPE_TEXT = 1  # local_type 低 32 位：1=文本

# 4.x local_type 低 32 位类型枚举（沿用微信消息类型体系，随真机样本校准）
_BASE_TYPES = {
    1: "text", 3: "image", 34: "voice", 42: "contact_card", 43: "video",
    47: "emoji", 48: "location", 49: "appmsg", 51: "system",
    10000: "system", 10002: "system",
}


def parse_rich(msg_type: str, content: str) -> tuple[str, dict]:
    """微信 XML 富内容 → (友好展示文本, 结构化元数据)。解析失败原样返回。

    对齐 PRD 3.3：content 存展示占位/标题，media_meta 存结构化字段，
    原始 XML 已由调用方保底存 raw。
    """
    meta: dict = {"kind": msg_type}
    if not (isinstance(content, str) and "<" in content):
        return content, meta
    import xml.etree.ElementTree as ET

    # 去掉 openim 等渠道的 "id@openim: " 前缀行：从第一个 "<" 起解析
    content = content[content.index("<"):]
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return "[卡片消息]", meta

    def _child_text(parent, tag: str) -> str:
        node = parent.find(tag) if parent is not None else None
        return (node.text or "").strip() if node is not None and node.text else ""

    # 语音：voicelength 在 voicemsg 子节点属性（部分版本在根节点，两处都取）
    if msg_type == "voice":
        node = root.find("voicemsg")
        if node is None:
            node = root
        seconds = int(int(node.attrib.get("voicelength", "0") or 0) / 1000)
        meta.update({"duration_seconds": seconds})
        return f"[语音] {seconds} 秒", meta
    if msg_type == "image":
        img = root.find("img")
        size = int(img.attrib.get("length", "0") or 0) if img is not None else 0
        meta.update({"size_bytes": size})
        return "[图片]", meta
    if msg_type == "video":
        v = root.find("videomsg")
        seconds = int(v.attrib.get("playlength", "0") or 0) if v is not None else 0
        meta.update({"duration_seconds": seconds})
        return f"[视频] {seconds} 秒", meta
    if msg_type == "emoji":
        return "[表情]", meta
    if msg_type == "location":
        label = root.attrib.get("label", "") or root.attrib.get("poiname", "")
        meta.update({"label": label})
        return f"[位置] {label}"[:120], meta

    # appmsg 家族：卡片 / 文件 / 引用
    appmsg = root.find("appmsg")
    if appmsg is None:
        return "[卡片消息]", meta
    title = _child_text(appmsg, "title")
    des = _child_text(appmsg, "des")
    url = _child_text(appmsg, "url")
    app_type = _child_text(appmsg, "type") or "0"
    meta.update({"title": title[:200], "url": url or None, "app_type": app_type})
    if url:
        meta["url"] = url

    refer = appmsg.find("refermsg")
    if refer is not None:
        who = _child_text(refer, "displayname")
        what = _child_text(refer, "content")
        if len(what) > 60:
            what = what[:60] + "…"
        meta["quote"] = {"who": who, "content": what}
        display = f"[引用] {who}：{what}"
        reply = _child_text(appmsg, "content")
        if reply:
            display += "\n↪ " + reply[:120]
        return display, meta

    if app_type == "6":  # 文件
        attach = appmsg.find("appattach")
        size = 0
        if attach is not None:
            size = int(_child_text(attach, "totallen") or 0)
        meta.update({"kind": "file", "filename": title, "size_bytes": size})
        return f"[文件] {title}", meta

    if title:
        display = f"[卡片] {title}"
        if des:
            display += "\n" + des[:120]
        meta["kind"] = "card"
        return display, meta
    return "[卡片消息]", meta


class WeChat4Source:
    """读取 decrypt_wechat4.py 产出的明文库。"""

    def __init__(self, plain_dir: str):
        self.root = Path(plain_dir)
        if not self.root.is_dir():
            raise RuntimeError(
                f"明文库目录不存在：{self.root}（先运行 scripts/decrypt_wechat4.py）"
            )
        self._name_cache: dict[str, str] | None = None

    # ---- 基础 ----

    def _conn(self, rel: str) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.root / rel))
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return row is not None

    def _contact_names(self) -> dict[str, str]:
        """username → 备注/昵称（contact.db）。"""
        if self._name_cache is not None:
            return self._name_cache
        names: dict[str, str] = {}
        contact_db = self.root / "contact" / "contact.db"
        if contact_db.is_file():
            conn = self._conn(str(contact_db.relative_to(self.root)))
            try:
                if self._table_exists(conn, "contact"):
                    for row in conn.execute("SELECT username, nick_name, remark FROM contact"):
                        names[row["username"]] = row["remark"] or row["nick_name"] or ""
            finally:
                conn.close()
        self._name_cache = names
        return names

    @staticmethod
    def _talker_table(talker: str) -> str:
        return f"Msg_{hashlib.md5(talker.encode()).hexdigest()}"

    # ---- DecryptSource 协议 ----

    def list_sessions(self) -> list[SessionInfo]:
        names = self._contact_names()
        sessions: dict[str, SessionInfo] = {}
        # 会话来源一：message 库中实际有 Msg_ 表的会话（以有数据为准）
        msg_dir = self.root / "message"
        for db_file in sorted(msg_dir.glob("message_*.db")) if msg_dir.is_dir() else []:
            rel = str(db_file.relative_to(self.root))
            conn = self._conn(rel)
            try:
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                        ("Msg_%",),
                    )
                ]
            finally:
                conn.close()
            by_table = {self._talker_table(username): username for username in list(names)}
            # Name2Id 里可能有未加联系人的会话对象，一并纳入反查
            conn = self._conn(rel)
            try:
                if self._table_exists(conn, "Name2Id"):
                    for (username,) in conn.execute("SELECT user_name FROM Name2Id"):
                        if username:
                            by_table.setdefault(self._talker_table(username), username)
            finally:
                conn.close()
            for table in tables:
                talker = by_table.get(table)
                if talker is None:
                    log.debug("无法反查表 %s 的会话，跳过", table)
                    continue
                stype = "group" if talker.endswith("@chatroom") else "dm"
                sessions[talker] = SessionInfo(talker, stype, names.get(talker, "") or talker)
        # 会话来源二：联系人中的群（白名单可先配置，等消息同步后即有数据）
        for username, name in names.items():
            if username.endswith("@chatroom") and username not in sessions:
                sessions[username] = SessionInfo(username, "group", name or username)
        return sorted(sessions.values(), key=lambda s: s.wx_id)

    def iter_messages(
        self, session: SessionInfo, since: datetime | None = None
    ) -> Iterator[RawMessage]:
        table = self._talker_table(session.wx_id)
        self._contact_names()
        msg_dir = self.root / "message"
        for db_file in sorted(msg_dir.glob("message_*.db")) if msg_dir.is_dir() else []:
            conn = self._conn(str(db_file.relative_to(self.root)))
            try:
                if not self._table_exists(conn, table):
                    continue
                id2name = {}
                if self._table_exists(conn, "Name2Id"):
                    id2name = {
                        rid: uname
                        for rid, uname in conn.execute("SELECT rowid, user_name FROM Name2Id")
                    }
                sql = (
                    f"SELECT server_id, real_sender_id, local_type, message_content, "
                    f"WCDB_CT_message_content, create_time FROM '{table}'"
                )
                params: list = []
                if since is not None:
                    sql += " WHERE create_time > ?"
                    params.append(int(since.timestamp()))
                sql += " ORDER BY create_time, server_id"
                for row in conn.execute(sql, params):
                    content = self._content(
                        row["message_content"], row["WCDB_CT_message_content"]
                    )
                    # openim 渠道文本消息带 "id@openim: " 前缀行，展示时去除
                    if row["local_type"] & 0xFFFFFFFF == 1:
                        content = re.sub(r"^\d+@openim:\s*", "", content)
                    msg_type = self._msg_type(row["local_type"], content)
                    if msg_type not in ("text", "system"):
                        content, media_meta = parse_rich(msg_type, content)
                    else:
                        media_meta = None
                    yield RawMessage(
                        session=session,
                        svr_id=str(row["server_id"]) if row["server_id"] else None,
                        sender_wxid=id2name.get(row["real_sender_id"]),
                        msg_type=msg_type,
                        content=content,
                        media_meta=media_meta or None,
                        ts=datetime.fromtimestamp(row["create_time"]),
                        raw={"local_type": row["local_type"]},
                    )
            finally:
                conn.close()

    @staticmethod
    def _msg_type(local_type: int, content) -> str:
        base = local_type & 0xFFFFFFFF
        if base == TYPE_TEXT:
            # openim 渠道消息带 "id@openim: " 前缀行，XML 在前缀之后
            if isinstance(content, str) and "<msg" in content:
                return "quote"
            return "text"
        return _BASE_TYPES.get(base, f"type_{base}")

    @staticmethod
    def _content(content, ct_flag: int) -> str:
        if isinstance(content, bytes) and ct_flag:
            import zstandard

            content = zstandard.ZstdDecompressor().decompress(content)
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return content or ""
