"""入库服务：批量去重（svr_id 优先、指纹兜底）+ sender_type 判定。

指纹仅在 server 端计算（设计决策 D8）；collector 不实现指纹算法。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ChatSession, Member, Message


def compute_fingerprint(wx_id: str, sender_wxid: str | None, ts: datetime, content: str) -> str:
    """兜底去重指纹。注意：同秒同内容存在理论碰撞，仅 svr_id 缺失时使用。"""
    basis = "|".join(
        [
            wx_id,
            sender_wxid or "",
            ts.strftime("%Y-%m-%d %H:%M:%S"),
            hashlib.sha256(content.encode()).hexdigest(),
        ]
    )
    return hashlib.sha256(basis.encode()).hexdigest()


def load_member_index(db: Session) -> tuple[set[str], set[str]]:
    """返回 (wxid 集合, 昵称/备注集合)。"""
    rows = db.execute(select(Member.match_type, Member.match_value)).all()
    wxids = {v for t, v in rows if t == "wxid"}
    names = {v for t, v in rows if t in ("nickname", "remark")}
    return wxids, names


def determine_sender_type(
    sender_wxid: str | None,
    msg_type: str,
    collector_wxid: str,
    member_wxids: set[str],
    member_names: set[str],
) -> str:
    if msg_type == "system" or not sender_wxid:
        return "system"
    if collector_wxid and sender_wxid == collector_wxid:
        return "me"
    if sender_wxid in member_wxids:
        return "internal"
    if sender_wxid in member_names:
        return "internal"
    return "external"


def upsert_session(db: Session, sess: dict[str, str]) -> ChatSession:
    wx_id = sess["wx_id"]
    obj = db.scalar(select(ChatSession).where(ChatSession.wx_id == wx_id))
    if obj is None:
        obj = ChatSession(wx_id=wx_id, type=sess.get("type", "group"), name=sess.get("name", ""))
        db.add(obj)
        db.flush()
    elif sess.get("name") and sess["name"] != obj.name:
        obj.name = sess["name"]  # 群名快照更新
    return obj


def ingest_batch(db: Session, messages: list[dict], collector_wxid: str) -> dict:
    """批量入库，返回 {inserted, skipped}。同批内也按 svr_id/fingerprint 去重。"""
    member_wxids, member_names = load_member_index(db)
    inserted = skipped = 0
    session_cache: dict[str, ChatSession] = {}
    seen_keys: set[str] = set()

    for m in messages:
        sess = session_cache.get(m["session"]["wx_id"])
        if sess is None:
            sess = upsert_session(db, m["session"])
            session_cache[m["session"]["wx_id"]] = sess

        fp = None
        if not m.get("svr_id"):
            fp = compute_fingerprint(
                sess.wx_id, m.get("sender_wxid"), m["ts"], m.get("content", "")
            )
        key = m.get("svr_id") or fp or ""
        if key in seen_keys:
            skipped += 1
            continue

        exists = False
        if m.get("svr_id"):
            exists = (
                db.scalar(
                    select(func.count()).select_from(Message).where(Message.svr_id == m["svr_id"])
                )
                > 0
            )
        elif fp:
            exists = (
                db.scalar(
                    select(func.count()).select_from(Message).where(Message.fingerprint == fp)
                )
                > 0
            )
        if exists:
            skipped += 1
            seen_keys.add(key)
            continue

        sender_type = determine_sender_type(
            m.get("sender_wxid"),
            m.get("msg_type", "text"),
            collector_wxid,
            member_wxids,
            member_names,
        )
        row = Message(
            session_id=sess.id,
            svr_id=m.get("svr_id"),
            fingerprint=fp,
            sender_wxid=m.get("sender_wxid"),
            sender_type=sender_type,
            msg_type=m.get("msg_type", "text"),
            content=m.get("content", ""),
            media_meta=m.get("media_meta"),
            ts=m["ts"],
            recalled=bool(m.get("recalled", False)),
            source=m.get("source", "decrypt"),
            raw=m.get("raw"),
        )
        db.add(row)
        db.flush()  # 拿 row.id；触发器同步 FTS
        if sess.last_msg_at is None or m["ts"] > sess.last_msg_at:
            sess.last_msg_at = m["ts"]
        m["_row_id"] = row.id
        m["_session_id"] = sess.id
        m["_sender_type"] = sender_type
        inserted += 1
        seen_keys.add(key)
    return {"inserted": inserted, "skipped": skipped}


def raw_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
