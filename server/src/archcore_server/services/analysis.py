"""分析服务：消息检索（FTS5 trigram + 2 字符 LIKE 回退）、仪表盘、客户总览、日聚合。"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from ..models import Alert, ChatSession, Customer, Message, MessageDaily, SyncTask

CURSOR_SEP = "|"


def encode_cursor(ts: datetime, id_: int) -> str:
    raw = json.dumps({"ts": ts.isoformat(sep=" "), "id": id_})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    raw = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return datetime.fromisoformat(raw["ts"]), int(raw["id"])


def _dt_str(ts: datetime) -> str:
    """与 SQLAlchemy SQLite DATETIME 存储格式一致的字符串（恒含 .ffffff），
    保证 text() 原生 SQL 中的字符串比较稳定，不依赖 DBAPI 的 datetime 适配。"""
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")


def search_messages(
    db: Session,
    session_id: int | None = None,
    q: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    sender_type: str | None = None,
    msg_type: str | None = None,
    customer_id: int | None = None,
    cursor: str | None = None,
    limit: int = 50,
    identity_role: str = "admin",
    identity_uid: int | None = None,
):
    """组合过滤检索，keyset 分页（ts, id 升序）。sales 角色收敛到自己客户。"""
    conditions = []
    params: dict = {}

    if q:
        q = q.strip()
        if len(q) >= 3:
            conditions.append("m.id IN (SELECT rowid FROM message_fts WHERE message_fts MATCH :q)")
            params["q"] = '"' + q.replace('"', "") + '"'
        else:
            conditions.append("m.content LIKE :qlike")
            params["qlike"] = f"%{q}%"
    if session_id is not None:
        conditions.append("m.session_id = :sid")
        params["sid"] = session_id
    if customer_id is not None:
        conditions.append("m.session_id IN (SELECT id FROM chat_session WHERE customer_id = :cid)")
        params["cid"] = customer_id
    if from_ts is not None:
        conditions.append("m.ts >= :from")
        params["from"] = _dt_str(from_ts)
    if to_ts is not None:
        conditions.append("m.ts <= :to")
        params["to"] = _dt_str(to_ts)
    if sender_type:
        conditions.append("m.sender_type = :stype")
        params["stype"] = sender_type
    if msg_type:
        conditions.append("m.msg_type = :mtype")
        params["mtype"] = msg_type
    if identity_role == "sales" and identity_uid is not None:
        conditions.append(
            "m.session_id IN (SELECT id FROM chat_session WHERE customer_id IN "
            "(SELECT id FROM customer WHERE owner_user_id = :uid))"
        )
        params["uid"] = identity_uid

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    if cursor:
        ts_c, id_c = decode_cursor(cursor)
        conditions.append("(m.ts > :cts OR (m.ts = :cts AND m.id > :cid))")
        params["cts"] = _dt_str(ts_c)
        params["cid"] = id_c
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"SELECT m.* FROM message m{where} ORDER BY m.ts, m.id LIMIT :limit"
    params["limit"] = limit + 1
    rows = db.execute(text(sql), params).mappings().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        encode_cursor(datetime.fromisoformat(rows[-1]["ts"]), rows[-1]["id"])
        if has_more and rows
        else None
    )
    return [dict(r) for r in rows], next_cursor


def message_context(db: Session, message_id: int, before: int = 20, after: int = 20):
    anchor = db.get(Message, message_id)
    if anchor is None:
        return None
    before_rows = db.scalars(
        select(Message)
        .where(
            Message.session_id == anchor.session_id,
            or_(Message.ts < anchor.ts, (Message.ts == anchor.ts) & (Message.id < anchor.id)),
        )
        .order_by(Message.ts.desc(), Message.id.desc())
        .limit(before)
    ).all()
    after_rows = db.scalars(
        select(Message)
        .where(
            Message.session_id == anchor.session_id,
            or_(Message.ts > anchor.ts, (Message.ts == anchor.ts) & (Message.id > anchor.id)),
        )
        .order_by(Message.ts.asc(), Message.id.asc())
        .limit(after)
    ).all()
    return list(reversed(before_rows)) + [anchor] + after_rows


def recompute_daily(db: Session, days: int = 3) -> int:
    """重算最近 N 天的 message_daily（jobs/aggregate 调用）。返回处理会话数。"""
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.execute(
        text(
            """
            SELECT m.session_id, date(m.ts) AS d,
                   COUNT(*) AS total,
                   SUM(CASE WHEN m.sender_type IN ('external') THEN 1 ELSE 0 END) AS ext_count,
                   SUM(CASE WHEN m.sender_type IN ('internal','me') THEN 1 ELSE 0 END) AS int_count
            FROM message m WHERE m.ts >= :since
            GROUP BY m.session_id, date(m.ts)
            """
        ),
        {"since": since},
    ).all()
    sessions_seen = set()
    for session_id, d, total, ext_count, int_count in rows:
        sessions_seen.add(session_id)
        obj = db.scalar(
            select(MessageDaily).where(
                MessageDaily.session_id == session_id, MessageDaily.date == d
            )
        )
        if obj is None:
            obj = MessageDaily(session_id=session_id, date=d)
            db.add(obj)
        obj.total, obj.ext_count, obj.int_count = total, ext_count, int_count
    db.commit()
    return len(sessions_seen)


def compute_reply_latencies(db: Session, session_id: int, days: int = 14) -> list[int]:
    """客户方发言 → 我方首次回复间隔（分钟），取最近 N 天。"""
    rows = db.scalars(
        select(Message)
        .where(
            Message.session_id == session_id, Message.ts >= datetime.utcnow() - timedelta(days=days)
        )
        .order_by(Message.ts, Message.id)
    ).all()
    latencies: list[int] = []
    pending_ext: Message | None = None
    for m in rows:
        if m.sender_type == "external":
            if pending_ext is not None:
                latencies.append(-1)  # 上一条客户消息未获回复，以 -1 标记未达标样本
            pending_ext = m
        elif m.sender_type in ("internal", "me") and pending_ext is not None:
            latencies.append(max(0, int((m.ts - pending_ext.ts).total_seconds() // 60)))
            pending_ext = None
    if pending_ext is not None:
        latencies.append(-1)  # 窗口结尾仍未回复
    return latencies


def dashboard(db: Session) -> dict:
    today = date.today().isoformat()
    total_customers = db.scalar(select(func.count()).select_from(Customer)) or 0
    claimed = (
        db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.customer_id.is_not(None))
        )
        or 0
    )
    unclaimed = (
        db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.customer_id.is_(None), ChatSession.type == "group")
        )
        or 0
    )
    today_msgs = (
        db.scalar(
            select(func.coalesce(func.sum(MessageDaily.total), 0)).where(MessageDaily.date == today)
        )
        or 0
    )
    trend = db.execute(
        text(
            "SELECT date, SUM(total) FROM message_daily"
            " WHERE date >= :since GROUP BY date ORDER BY date"
        ),
        {"since": (date.today() - timedelta(days=13)).isoformat()},
    ).all()
    level_dist = db.execute(
        text(
            "SELECT health_level, COUNT(*) FROM customer"
            " WHERE health_level IS NOT NULL GROUP BY health_level"
        )
    ).all()
    pending_alerts = db.scalars(
        select(Alert).where(Alert.status == "pending").order_by(Alert.created_at.desc()).limit(10)
    ).all()
    pending_count = (
        db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "pending")) or 0
    )
    last_sync = db.scalar(select(SyncTask).order_by(SyncTask.id.desc()).limit(1))
    return {
        "total_customers": total_customers,
        "claimed_sessions": claimed,
        "unclaimed_sessions": unclaimed,
        "today_messages": int(today_msgs),
        "trend": [{"date": d, "total": int(t or 0)} for d, t in trend],
        "health_distribution": {lvl: n for lvl, n in level_dist},
        "pending_alerts": [
            {
                "id": a.id,
                "rule_code": a.rule_code,
                "level": a.level,
                "customer_id": a.customer_id,
                "created_at": a.created_at.isoformat(),
            }
            for a in pending_alerts
        ],
        "pending_alert_count": int(pending_count),
        "last_sync": (
            {
                "type": last_sync.type,
                "status": last_sync.status,
                "at": (last_sync.finished_at or last_sync.created_at).isoformat(),
            }
            if last_sync
            else None
        ),
    }


def customer_overview(db: Session, customer_id: int) -> dict:
    sessions = db.scalars(select(ChatSession).where(ChatSession.customer_id == customer_id)).all()
    trend = db.execute(
        text(
            """
            SELECT md.date, SUM(md.total) AS total, SUM(md.ext_count) AS ext
            FROM message_daily md
            WHERE md.session_id IN (SELECT id FROM chat_session WHERE customer_id = :cid)
              AND md.date >= :since
            GROUP BY md.date ORDER BY md.date
            """
        ),
        {"cid": customer_id, "since": (date.today() - timedelta(days=29)).isoformat()},
    ).all()
    latencies: list[int] = []
    for s in sessions:
        latencies.extend(compute_reply_latencies(db, s.id))
    on_time = [x for x in latencies if x >= 0]
    return {
        "session_count": len(sessions),
        "trend": [{"date": d, "total": int(t or 0), "external": int(e or 0)} for d, t, e in trend],
        "response": {
            "samples": len(latencies),
            "p50_minutes": _percentile(on_time, 50),
            "p90_minutes": _percentile(on_time, 90),
            "sla_rate": round(len(on_time) / len(latencies), 3) if latencies else None,
        },
    }


def _percentile(values: list[int], p: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * p / 100))
    return ordered[idx]
