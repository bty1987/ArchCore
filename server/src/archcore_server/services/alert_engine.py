"""预警引擎：触发型（消息驱动）+ 巡检型（时间驱动），每规则带冷却。

触发型在 ingest 事务内同步评估；巡检型由 jobs/inspectors 定时调用。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert, AlertRule, ChatSession, Customer, Keyword, Message
from .notify import dispatch_alert

DEFAULT_RULES: list[dict] = [
    {"code": "risk_keyword", "level": "red", "cooldown_minutes": 60, "params": {}},
    {
        "code": "response_timeout",
        "level": "orange",
        "cooldown_minutes": 240,
        "params": {"timeout_minutes": 240, "work_start": 9, "work_end": 18},
    },
    {
        "code": "customer_silence",
        "level": "yellow",
        "cooldown_minutes": 7 * 24 * 60,
        "params": {"silent_days": 7},
    },
    {
        "code": "session_inactive",
        "level": "gray",
        "cooldown_minutes": 30 * 24 * 60,
        "params": {"inactive_days": 30},
    },
    {
        "code": "collect_stale",
        "level": "red",
        "cooldown_minutes": 60,
        "params": {"stale_minutes": 120},
    },
    {"code": "member_left", "level": "orange", "cooldown_minutes": 60, "params": {}},
]

LEVEL_RANK = {"gray": 0, "yellow": 1, "orange": 2, "red": 3}


def seed_rules(db: Session) -> None:
    for spec in DEFAULT_RULES:
        exists = db.scalar(select(AlertRule).where(AlertRule.code == spec["code"]))
        if exists is None:
            db.add(AlertRule(**spec))
    db.commit()


def _rule(db: Session, code: str) -> AlertRule | None:
    rule = db.scalar(select(AlertRule).where(AlertRule.code == code))
    return rule if rule is not None and rule.enabled else None


def _cooling(
    db: Session,
    code: str,
    rule: AlertRule,
    now: datetime,
    customer_id: int | None = None,
    session_id: int | None = None,
) -> bool:
    """冷却窗口内已有同规则预警则不再重复。"""
    since = now - timedelta(minutes=rule.cooldown_minutes)
    q = select(Alert).where(Alert.rule_code == code, Alert.created_at >= since)
    if customer_id is not None:
        q = q.where(Alert.customer_id == customer_id)
    if session_id is not None:
        q = q.where(Alert.session_id == session_id)
    return db.scalar(q.limit(1)) is not None


def create_alert(
    db: Session,
    code: str,
    level: str,
    detail: dict,
    customer_id: int | None = None,
    session_id: int | None = None,
    message_id: int | None = None,
    force: bool = False,
) -> Alert | None:
    now = datetime.utcnow()
    rule = db.scalar(select(AlertRule).where(AlertRule.code == code))
    if not force:
        if rule is None or not rule.enabled:
            return None
        if _cooling(db, code, rule, now, customer_id, session_id):
            return None
    alert = Alert(
        rule_code=code,
        level=level,
        customer_id=customer_id,
        session_id=session_id,
        message_id=message_id,
        detail=detail,
        created_at=now,
    )
    db.add(alert)
    db.flush()
    dispatch_alert(db, alert)
    return alert


def work_minutes_between(
    start: datetime, end: datetime, wh_start: int = 9, wh_end: int = 18
) -> int:
    """工作时间段分钟数（工作日 wh_start~wh_end）。响应时效的工作时间口径。"""
    if end <= start:
        return 0
    minutes = 0
    cur = start.replace(minute=0, second=0, microsecond=0)
    total_hours = max(0.0, (end - cur).total_seconds() / 3600.0) + (start.minute / 60.0)
    # 逐日切分（跨度通常 <= 数天，性能可接受）
    day = start.date()
    while day <= end.date():
        if day.weekday() < 5:  # 周一~周五
            ws = datetime(day.year, day.month, day.day, wh_start)
            we = datetime(day.year, day.month, day.day, wh_end)
            lo, hi = max(start, ws), min(end, we)
            if hi > lo:
                minutes += int((hi - lo).total_seconds() // 60)
        day += timedelta(days=1)
    del total_hours
    return minutes


def evaluate_triggers(db: Session, messages: list[dict]) -> list[Alert]:
    """ingest 后同步评估触发型规则（仅对本次新插入消息）。"""
    fired: list[Alert] = []
    for m in messages:
        if "_row_id" not in m:
            continue
        session_id = m["_session_id"]
        row_id = m["_row_id"]
        ts: datetime = m["ts"]
        sess = db.get(ChatSession, session_id)
        customer_id = sess.customer_id if sess else None

        # 规则一：风险词命中（仅文本、外部消息）
        if m["_sender_type"] == "external" and m.get("msg_type") == "text" and m.get("content"):
            words = [
                k.word
                for k in db.scalars(
                    select(Keyword).where(Keyword.category == "risk", Keyword.enabled.is_(True))
                ).all()
            ]
            hit = next((w for w in words if w.lower() in m["content"].lower()), None)
            if hit:
                alert = create_alert(
                    db,
                    "risk_keyword",
                    "red",
                    {"keyword": hit, "preview": m["content"][:100], "ts": ts.isoformat()},
                    customer_id=customer_id,
                    session_id=session_id,
                    message_id=row_id,
                )
                if alert:
                    fired.append(alert)

        # 规则二：响应超时——本次外部消息到达时，检查上一条外部消息至今是否仍无我方回复
        if m["_sender_type"] == "external":
            prev_ext = db.scalar(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.sender_type == "external",
                    Message.id < row_id,
                )
                .order_by(Message.id.desc())
                .limit(1)
            )
            if prev_ext is not None:
                rule = _rule(db, "response_timeout")
                if rule is not None:
                    timeout = rule.params.get("timeout_minutes", 240)
                    wh_start = rule.params.get("work_start", 9)
                    wh_end = rule.params.get("work_end", 18)
                    waited = work_minutes_between(prev_ext.ts, ts, wh_start, wh_end)
                    replied = db.scalar(
                        select(Message.id)
                        .where(
                            Message.session_id == session_id,
                            Message.sender_type.in_(("internal", "me")),
                            Message.id > prev_ext.id,
                            Message.id < row_id,
                        )
                        .limit(1)
                    )
                    if replied is None and waited >= timeout:
                        alert = create_alert(
                            db,
                            "response_timeout",
                            "orange",
                            {"waited_minutes": waited, "since": prev_ext.ts.isoformat()},
                            customer_id=customer_id,
                            session_id=session_id,
                            message_id=prev_ext.id,
                        )
                        if alert:
                            fired.append(alert)
    return fired


def silence_inspection(db: Session, now: datetime | None = None) -> int:
    """巡检：客户沉默（客户方连续 N 天无发言）。返回产生预警数。"""
    now = now or datetime.utcnow()
    rule = _rule(db, "customer_silence")
    if rule is None:
        return 0
    silent_days = rule.params.get("silent_days", 7)
    count = 0
    customers = db.scalars(select(Customer)).all()
    for c in customers:
        last_ext = db.scalar(
            select(Message.ts)
            .join(ChatSession, ChatSession.id == Message.session_id)
            .where(ChatSession.customer_id == c.id, Message.sender_type == "external")
            .order_by(Message.ts.desc())
            .limit(1)
        )
        if last_ext is None:
            continue
        if (now - last_ext).days >= silent_days:
            alert = create_alert(
                db,
                "customer_silence",
                rule.level,
                {"silent_days": (now - last_ext).days, "last_external_at": last_ext.isoformat()},
                customer_id=c.id,
            )
            if alert:
                count += 1
    return count


def inactive_inspection(db: Session, now: datetime | None = None) -> int:
    """巡检：群长期不活跃（30 天无任何消息，建议归档）。"""
    now = now or datetime.utcnow()
    rule = _rule(db, "session_inactive")
    if rule is None:
        return 0
    inactive_days = rule.params.get("inactive_days", 30)
    count = 0
    sessions = db.scalars(select(ChatSession).where(ChatSession.status == "active")).all()
    for s in sessions:
        if s.last_msg_at is None:
            continue
        if (now - s.last_msg_at).days >= inactive_days:
            alert = create_alert(
                db,
                "session_inactive",
                rule.level,
                {"inactive_days": (now - s.last_msg_at).days},
                customer_id=s.customer_id,
                session_id=s.id,
            )
            if alert:
                count += 1
    return count


def collect_stale_inspection(db: Session, now: datetime | None = None) -> int:
    """巡检：采集异常（最近一次 sync_task 超过阈值）。"""
    from ..models import SyncTask

    now = now or datetime.utcnow()
    rule = _rule(db, "collect_stale")
    if rule is None:
        return 0
    stale_minutes = rule.params.get("stale_minutes", 120)
    last = db.scalar(select(SyncTask).order_by(SyncTask.created_at.desc()).limit(1))
    if last is None:
        return 0
    ref = last.finished_at or last.created_at
    if (now - ref).total_seconds() / 60 >= stale_minutes:
        alert = create_alert(
            db,
            "collect_stale",
            rule.level,
            {
                "last_sync_at": ref.isoformat(),
                "stale_minutes": int((now - ref).total_seconds() / 60),
            },
        )
        return 1 if alert else 0
    return 0
