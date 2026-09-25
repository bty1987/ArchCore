"""分析与仪表盘 + 预警 + 通知 + 采集上报路由（合并小模块）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import LEVEL_ORDER, get_settings
from ..core.security import current_user, get_identity
from ..models import (
    Alert,
    AlertRule,
    AuditLog,
    ChatSession,
    NotifyChannel,
    SyncTask,
    WhitelistRule,
)
from ..schemas import (
    AlertHandleIn,
    AlertOut,
    AlertRuleIn,
    AllowAllIn,
    IngestBatchIn,
    IngestBatchOut,
    InventoryIn,
    NotifyChannelIn,
    SyncTaskIn,
)
from ..services import alert_engine, analysis
from ..services import ingest as ingest_svc
from ..services import notify as notify_svc
from .deps import (
    get_session,
    manager_identity,
    require_collector_or_user,
    require_collector_token,
    user_identity,
)

router = APIRouter(tags=["analytics", "alerts", "notify", "ingest"])


# ---------- 分析 ----------


@router.get("/dashboard")
def dashboard(identity: dict = Depends(user_identity), db: Session = Depends(get_session)):
    current_user(identity, db)
    return analysis.dashboard(db)


@router.get("/analytics/trends")
def trends(
    days: int = Query(30, le=365),
    customer_id: int | None = None,
    identity: dict = Depends(user_identity),
    db: Session = Depends(get_session),
):
    from datetime import date, timedelta

    from sqlalchemy import text

    current_user(identity, db)
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    sql = (
        "SELECT md.date, SUM(md.total) AS total, SUM(md.ext_count) AS ext "
        "FROM message_daily md WHERE md.date >= :since"
    )
    params: dict = {"since": since}
    if customer_id:
        sql += " AND md.session_id IN (SELECT id FROM chat_session WHERE customer_id = :cid)"
        params["cid"] = customer_id
    sql += " GROUP BY md.date ORDER BY md.date"
    rows = db.execute(text(sql), params).all()
    return [{"date": d, "total": int(t or 0), "external": int(e or 0)} for d, t, e in rows]


@router.get("/analytics/customers/{customer_id}/overview")
def customer_overview(
    customer_id: int, identity: dict = Depends(user_identity), db: Session = Depends(get_session)
):
    current_user(identity, db)
    if identity["role"] == "sales":
        from ..models import Customer

        c = db.get(Customer, customer_id)
        if c is None or c.owner_user_id != identity["uid"]:
            raise HTTPException(403, "无权访问该客户")
    return analysis.customer_overview(db, customer_id)


# ---------- 预警 ----------


@router.get("/alert-rules")
def list_rules(identity: dict = Depends(user_identity), db: Session = Depends(get_session)):
    return db.scalars(select(AlertRule)).all()


@router.put("/alert-rules/{code}")
def update_rule(
    code: str,
    body: AlertRuleIn,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    rule = db.scalar(select(AlertRule).where(AlertRule.code == code))
    if rule is None:
        raise HTTPException(404, "规则不存在")
    rule.level, rule.enabled = body.level, body.enabled
    rule.cooldown_minutes = body.cooldown_minutes
    rule.params = body.params or rule.params
    db.add(
        AuditLog(
            user_id=identity["uid"],
            action="alert_rule_update",
            target=code,
            detail={"enabled": body.enabled, "level": body.level},
        )
    )
    db.commit()
    return rule


@router.get("/alerts")
def list_alerts(
    status: str | None = Query(None),
    level: str | None = None,
    customer_id: int | None = None,
    limit: int = Query(50, le=200),
    identity: dict = Depends(user_identity),
    db: Session = Depends(get_session),
):
    current_user(identity, db)
    query = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        query = query.where(Alert.status == status)
    if level:
        query = query.where(Alert.level == level)
    if customer_id:
        query = query.where(Alert.customer_id == customer_id)
    if identity["role"] == "sales":
        query = query.where(
            Alert.customer_id.in_(select(_cust_id()).where(_cust_owner() == identity["uid"]))
        )
    rows = db.scalars(query).all()
    return [AlertOut.model_validate(a) for a in rows]


def _cust_id():
    from ..models import Customer

    return Customer.id


def _cust_owner():
    from ..models import Customer

    return Customer.owner_user_id


@router.post("/alerts/{alert_id}/handle")
def handle_alert(
    alert_id: int,
    body: AlertHandleIn,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "预警不存在")
    if body.action not in ("handled", "ignored"):
        raise HTTPException(422, "action 须为 handled/ignored")
    alert.status = body.action
    alert.handle_note = body.note
    alert.handled_by = identity["uid"]
    alert.handled_at = datetime.utcnow()
    db.add(
        AuditLog(
            user_id=identity["uid"],
            action="alert_handle",
            target=f"alert:{alert_id}",
            detail={"action": body.action, "note": body.note},
        )
    )
    db.commit()
    return AlertOut.model_validate(alert)


# ---------- 通知 ----------


@router.get("/notifications")
def notifications(identity: dict = Depends(get_identity), db: Session = Depends(get_session)):
    from ..models import InAppNotification

    current_user(identity, db)
    rows = db.scalars(
        select(InAppNotification)
        .where(InAppNotification.user_id == identity["uid"])
        .order_by(InAppNotification.created_at.desc())
        .limit(50)
    ).all()
    return {
        "unread": notify_svc.unread_count(db, identity["uid"]),
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "alert_id": n.alert_id,
                "read_at": n.read_at,
                "created_at": n.created_at,
            }
            for n in rows
        ],
    }


@router.post("/notifications/read")
def notifications_read(identity: dict = Depends(get_identity), db: Session = Depends(get_session)):
    return {"marked": notify_svc.mark_read(db, identity["uid"])}


@router.get("/notify-channels")
def list_channels(identity: dict = Depends(manager_identity), db: Session = Depends(get_session)):
    return db.scalars(select(NotifyChannel)).all()


@router.post("/notify-channels")
def create_channel(
    body: NotifyChannelIn,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    if body.type not in ("email", "wecom"):
        raise HTTPException(422, "type 须为 email/wecom")
    if body.min_level not in LEVEL_ORDER:
        raise HTTPException(422, "min_level 无效")
    ch = NotifyChannel(
        type=body.type,
        name=body.name,
        config=body.config,
        min_level=body.min_level,
        enabled=body.enabled,
    )
    db.add(ch)
    db.commit()
    return {"id": ch.id}


@router.post("/notify-channels/{channel_id}/test")
def test_channel(
    channel_id: int, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    status_, error = notify_svc.send_test(db, channel_id)
    return {"status": status_, "error": error}


@router.get("/analytics/keywords/stats")
def keyword_stats(days: int = Query(30, le=365), identity: dict = Depends(user_identity),
                  db: Session = Depends(get_session)):
    """词库命中统计：全库范围按词计数（词库管理页与售前口径使用）。"""
    from ..models import Keyword

    current_user(identity, db)
    from datetime import date, timedelta

    from sqlalchemy import text as _text

    since = str(date.today() - timedelta(days=days - 1))
    out = []
    for kw in db.scalars(
        select(Keyword).where(Keyword.enabled.is_(True))
    ).all():
        cnt = db.execute(
            _text(
                "SELECT COUNT(*) FROM message "
                "WHERE content LIKE :pat AND ts >= :since"
            ),
            {"pat": f"%{kw.word}%", "since": since},
        ).scalar()
        out.append({"word": kw.word, "category": kw.category, "count": int(cnt)})
    out.sort(key=lambda x: -x["count"])
    return out


# ---------- 会话白名单（服务端管控，采集端每轮拉取） ----------


def _allow_all(db: Session) -> bool:
    from ..models import AppSetting

    row = db.get(AppSetting, "whitelist_allow_all")
    return bool(row and row.value.get("enabled"))


@router.get("/whitelist")
def get_whitelist(identity: dict = Depends(manager_identity), db: Session = Depends(get_session)):
    current_user(identity, db)
    rules = db.scalars(select(WhitelistRule).order_by(WhitelistRule.id.desc())).all()
    return {
        "allow_all": _allow_all(db),
        "rules": [
            {
                "id": r.id,
                "wx_id": r.wx_id,
                "stype": r.stype,
                "name": r.name,
                "note": r.note,
                "enabled": r.enabled,
            }
            for r in rules
        ],
    }


@router.put("/whitelist/allow-all")
def set_allow_all(
    body: AllowAllIn, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    from ..models import AppSetting

    row = db.get(AppSetting, "whitelist_allow_all")
    if row is None:
        row = AppSetting(key="whitelist_allow_all")
        db.add(row)
    row.value = {"enabled": body.enabled}
    db.add(
        AuditLog(
            user_id=identity["uid"], action="whitelist_allow_all", detail={"enabled": body.enabled}
        )
    )
    db.commit()
    return {"allow_all": body.enabled}


@router.post("/whitelist")
def add_whitelist_rule(
    body: dict, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    wx_id = str(body.get("wx_id", "")).strip()
    stype = body.get("stype", "group")
    if not wx_id:
        raise HTTPException(422, "wx_id 必填")
    if stype not in ("group", "dm"):
        raise HTTPException(422, "stype 须为 group/dm")
    rule = db.scalar(select(WhitelistRule).where(WhitelistRule.wx_id == wx_id))
    if rule is None:
        rule = WhitelistRule(wx_id=wx_id, stype=stype)
        db.add(rule)
    rule.stype = stype
    rule.name = str(body.get("name", "")) or rule.name
    rule.note = str(body.get("note", "")) or rule.note
    rule.enabled = bool(body.get("enabled", True))
    db.add(AuditLog(user_id=identity["uid"], action="whitelist_add", target=wx_id))
    db.commit()
    return {"id": rule.id, "wx_id": rule.wx_id}


@router.delete("/whitelist/{rule_id}")
def delete_whitelist_rule(
    rule_id: int, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    rule = db.get(WhitelistRule, rule_id)
    if rule:
        db.delete(rule)
        db.add(AuditLog(user_id=identity["uid"], action="whitelist_delete", target=rule.wx_id))
        db.commit()
    return {"deleted": rule_id}


# ---------- 采集上报（collector 专用，独立 token） ----------


@router.get("/ingest/whitelist")
def ingest_whitelist(
    _tok: None = Depends(require_collector_token), db: Session = Depends(get_session)
):
    """采集端每轮同步前拉取生效白名单。"""
    rules = db.scalars(select(WhitelistRule).where(WhitelistRule.enabled.is_(True))).all()
    return {
        "allow_all": _allow_all(db),
        "groups": [r.wx_id for r in rules],  # 群与单聊 wx_id 通用（语义见 transform/filter）
    }


@router.post("/ingest/sessions")
def ingest_sessions(
    body: InventoryIn,
    _tok: None = Depends(require_collector_token),
    db: Session = Depends(get_session),
):
    """采集端上报发现的会话清单（含尚无消息的群），供白名单页与待认领使用。"""
    known = 0
    for item in body.sessions:
        obj = db.scalar(select(ChatSession).where(ChatSession.wx_id == item.wx_id))
        if obj is None:
            db.add(ChatSession(wx_id=item.wx_id, type=item.type, name=item.name))
            known += 1
        elif item.name and item.name != obj.name:
            obj.name = item.name
    db.commit()
    return {"known": known, "received": len(body.sessions)}


@router.post("/ingest/messages", response_model=IngestBatchOut)
def ingest_messages(
    body: IngestBatchIn,
    _tok: None = Depends(require_collector_token),
    db: Session = Depends(get_session),
):
    settings = get_settings()
    messages = [
        {
            "session": m.session,
            "svr_id": m.svr_id,
            "sender_wxid": m.sender_wxid,
            "msg_type": m.msg_type,
            "content": m.content,
            "ts": m.ts,
            "source": m.source,
            "recalled": m.recalled,
            "media_meta": m.media_meta,
            "raw": m.raw,
        }
        for m in body.messages
    ]
    stats = ingest_svc.ingest_batch(db, messages, settings.collector_wxid)
    # 触发型预警评估（同事务）
    alert_engine.evaluate_triggers(db, messages)
    db.commit()
    return IngestBatchOut(**stats)


@router.post("/ingest/sync-tasks")
def ingest_sync_task(
    body: SyncTaskIn,
    x_collector_wxid: str = Header(default=""),
    _tok: None = Depends(require_collector_token),
    db: Session = Depends(get_session),
):
    task = SyncTask(
        type=body.type,
        status=body.status,
        stats=body.stats,
        log=body.log,
        collector_wxid=x_collector_wxid,
        finished_at=datetime.utcnow() if body.status != "running" else None,
    )
    db.add(task)
    db.commit()
    return {"id": task.id}


@router.get("/ingest/health")
def ingest_health(
    _tok: None = Depends(require_collector_or_user), db: Session = Depends(get_session)
):
    last = db.scalar(select(SyncTask).order_by(SyncTask.id.desc()).limit(1))
    msg_count = db.scalar(select(func.count()).select_from(_msg_table())) or 0
    return {
        "last_sync": (
            {
                "type": last.type,
                "status": last.status,
                "at": (last.finished_at or last.created_at).isoformat(),
            }
            if last
            else None
        ),
        "message_count": int(msg_count),
    }


def _msg_table():
    from ..models import Message

    return Message
