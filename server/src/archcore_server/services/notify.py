"""通知分发：站内（必发）+ 渠道外发（达到 min_level 才发），全部留痕 notify_record。"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert, AppUser, Customer, InAppNotification, NotifyChannel, NotifyRecord

log = logging.getLogger(__name__)

LEVEL_TITLE = {
    "risk_keyword": "风险词命中",
    "response_timeout": "响应超时",
    "customer_silence": "客户沉默",
    "session_inactive": "群长期不活跃",
    "collect_stale": "采集异常",
    "member_left": "客户方成员退群",
}


def dispatch_alert(db: Session, alert: Alert) -> None:
    """告警创建后的分发：站内通知负责人/管理员；外发渠道按级别过滤。"""
    from ..core.config import get_settings

    settings = get_settings()
    customer = db.get(Customer, alert.customer_id) if alert.customer_id else None
    title = f"[{alert.level}] {LEVEL_TITLE.get(alert.rule_code, alert.rule_code)}"
    body = f"{customer.name if customer else '未映射会话'}：{alert.detail}"

    # 站内：客户负责人；无负责人则全体 admin
    recipient_ids: set[int] = set()
    if customer is not None and customer.owner_user_id:
        recipient_ids.add(customer.owner_user_id)
    else:
        admin_ids = db.scalars(
            select(AppUser.id).where(AppUser.role == "admin", AppUser.enabled.is_(True))
        ).all()
        recipient_ids.update(admin_ids)
    for uid in recipient_ids:
        db.add(InAppNotification(user_id=uid, alert_id=alert.id, title=title, body=body))

    # 外发渠道
    channels = db.scalars(select(NotifyChannel).where(NotifyChannel.enabled.is_(True))).all()
    for ch in channels:
        if ch.type == "inapp":
            continue
        if not settings.level_ge(alert.level, ch.min_level):
            record = NotifyRecord(
                alert_id=alert.id, channel=ch.type, target=ch.name, status="skipped"
            )
            db.add(record)
            continue
        status_, error = _send_channel(ch, title, body)
        db.add(
            NotifyRecord(
                alert_id=alert.id, channel=ch.type, target=ch.name, status=status_, error=error
            )
        )


def _send_channel(ch: NotifyChannel, title: str, body: str) -> tuple[str, str | None]:
    try:
        if ch.type == "wecom":
            url = ch.config.get("webhook_url", "")
            if not url:
                return "skipped", "未配置 webhook_url"
            resp = httpx.post(
                url,
                json={"msgtype": "markdown", "markdown": {"content": f"**{title}**\n{body}"}},
                timeout=10,
            )
            return (
                "sent" if resp.status_code == 200 else "failed"
            ), None if resp.status_code == 200 else resp.text
        if ch.type == "email":
            smtp = ch.config.get("smtp_host", "")
            if not smtp:
                return "skipped", "未配置 smtp"
            _send_email(ch.config, title, body)
            return "sent", None
        return "skipped", f"未知渠道类型 {ch.type}"
    except Exception as exc:  # 通知失败不阻断入库/预警主流程
        log.warning("notify %s failed: %s", ch.type, exc)
        return "failed", str(exc)


def _send_email(cfg: dict, title: str, body: str) -> None:
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = cfg.get("from", "")
    msg["To"] = ", ".join(cfg.get("to", []))
    with smtplib.SMTP(cfg["smtp_host"], cfg.get("smtp_port", 25), timeout=15) as server:
        if cfg.get("use_tls"):
            server.starttls()
        if cfg.get("username"):
            server.login(cfg["username"], cfg.get("password", ""))
        server.sendmail(msg["From"], cfg.get("to", []), msg.as_string())


def send_test(db: Session, channel_id: int) -> tuple[str, str | None]:
    ch = db.get(NotifyChannel, channel_id)
    status_, error = _send_channel(ch, "ArchCore 测试通知", "这是一条测试消息。")
    db.add(NotifyRecord(alert_id=0, channel=ch.type, target=ch.name, status=status_, error=error))
    db.commit()
    return status_, error


def unread_count(db: Session, user_id: int) -> int:
    from sqlalchemy import func

    return (
        db.scalar(
            select(func.count())
            .select_from(InAppNotification)
            .where(InAppNotification.user_id == user_id, InAppNotification.read_at.is_(None))
        )
        or 0
    )


def mark_read(db: Session, user_id: int, ids: list[int] | None = None) -> int:
    now = datetime.utcnow()
    q = select(InAppNotification).where(
        InAppNotification.user_id == user_id, InAppNotification.read_at.is_(None)
    )
    if ids:
        q = q.where(InAppNotification.id.in_(ids))
    rows = db.scalars(q).all()
    for r in rows:
        r.read_at = now
    db.commit()
    return len(rows)
