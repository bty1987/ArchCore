"""映射服务：待认领列表、群→客户映射、单聊联系人挂靠。全操作写审计。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AuditLog, ChatSession, Contact, Customer, Message


def list_unclaimed(db: Session) -> list[dict]:
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.customer_id.is_(None), ChatSession.status == "active")
        .order_by(ChatSession.last_msg_at.desc())
    ).all()
    out = []
    for s in sessions:
        count = (
            db.scalar(select(func.count()).select_from(Message).where(Message.session_id == s.id))
            or 0
        )
        out.append(
            {
                "id": s.id,
                "wx_id": s.wx_id,
                "type": s.type,
                "name": s.name,
                "last_msg_at": s.last_msg_at,
                "message_count": int(count),
            }
        )
    return out


def map_session(
    db: Session, session_id: int, customer_id: int | None, user_id: int | None
) -> ChatSession:
    sess = db.get(ChatSession, session_id)
    if sess is None:
        raise ValueError("会话不存在")
    if customer_id is not None and db.get(Customer, customer_id) is None:
        raise ValueError("客户不存在")
    old = sess.customer_id
    sess.customer_id = customer_id
    db.add(
        AuditLog(
            user_id=user_id,
            action="session_map",
            target=f"session:{session_id}",
            detail={"from": old, "to": customer_id},
        )
    )
    db.commit()
    db.refresh(sess)
    return sess


def claim_sessions(
    db: Session, customer_id: int, session_ids: list[int], user_id: int | None
) -> int:
    n = 0
    for sid in session_ids:
        sess = db.get(ChatSession, sid)
        if sess is not None:
            sess.customer_id = customer_id
            n += 1
    db.add(
        AuditLog(
            user_id=user_id,
            action="customer_claim",
            target=f"customer:{customer_id}",
            detail={"session_ids": session_ids},
        )
    )
    db.commit()
    return n


def attach_contact(
    db: Session, wx_id: str, customer_id: int, nickname: str = "", remark: str = ""
) -> Contact:
    obj = db.scalar(select(Contact).where(Contact.wx_id == wx_id))
    if obj is None:
        obj = Contact(wx_id=wx_id, nickname=nickname, remark=remark, customer_id=customer_id)
    else:
        obj.customer_id = customer_id
        obj.nickname = nickname or obj.nickname
        obj.remark = remark or obj.remark
    db.add(obj)
    db.commit()
    return obj
