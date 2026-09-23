"""导出服务：CSV / HTML，全部写审计日志（数据红线）。"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, ChatSession, Message


def export_messages_csv(
    db: Session,
    session_id: int,
    from_ts: datetime | None,
    to_ts: datetime | None,
    user_id: int | None,
) -> tuple[str, io.StringIO]:
    sess = db.get(ChatSession, session_id)
    if sess is None:
        raise ValueError("会话不存在")
    q = select(Message).where(Message.session_id == session_id)
    if from_ts:
        q = q.where(Message.ts >= from_ts)
    if to_ts:
        q = q.where(Message.ts <= to_ts)
    rows = db.scalars(q.order_by(Message.ts, Message.id)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ts", "sender_wxid", "sender_type", "msg_type", "recalled", "content"])
    for m in rows:
        writer.writerow(
            [
                m.id,
                m.ts.isoformat(sep=" "),
                m.sender_wxid or "",
                m.sender_type,
                m.msg_type,
                int(m.recalled),
                m.content.replace("\n", " "),
            ]
        )
    db.add(
        AuditLog(
            user_id=user_id,
            action="export_csv",
            target=f"session:{session_id}",
            detail={
                "rows": len(rows),
                "from": from_ts and from_ts.isoformat(),
                "to": to_ts and to_ts.isoformat(),
            },
        )
    )
    db.commit()
    filename = f"session-{session_id}-{datetime.utcnow():%Y%m%d%H%M%S}.csv"
    return filename, buf


def export_customer_html(db: Session, customer_id: int, user_id: int | None) -> tuple[str, str]:
    from ..models import Customer

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ValueError("客户不存在")
    sessions = db.scalars(select(ChatSession).where(ChatSession.customer_id == customer_id)).all()
    parts = [
        "<html><head><meta charset='utf-8'><title>",
        customer.name,
        "</title></head><body><h1>",
        customer.name,
        "</h1>",
    ]
    total = 0
    for s in sessions:
        msgs = db.scalars(
            select(Message)
            .where(Message.session_id == s.id)
            .order_by(Message.ts, Message.id)
            .limit(5000)
        ).all()
        total += len(msgs)
        parts.append(f"<h2>{s.name or s.wx_id}</h2><ul>")
        parts.extend(
            f"<li><code>{m.ts:%Y-%m-%d %H:%M}</code> [{m.sender_type}] {m.content}</li>"
            for m in msgs
        )
        parts.append("</ul>")
    parts.append("</body></html>")
    db.add(
        AuditLog(
            user_id=user_id,
            action="export_html",
            target=f"customer:{customer_id}",
            detail={"rows": total},
        )
    )
    db.commit()
    filename = f"customer-{customer_id}-{datetime.utcnow():%Y%m%d%H%M%S}.html"
    return filename, "".join(parts)
