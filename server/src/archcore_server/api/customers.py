"""客户：CRUD + 认领会话 + 导出。sales 仅见自己负责的客户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.security import current_user, get_identity, require_roles
from ..models import AppUser, ChatSession, Customer
from ..schemas import ClaimIn, CustomerIn, CustomerOut
from ..services import exporter
from .deps import get_session, manager_identity, user_identity

router = APIRouter(prefix="/customers", tags=["customers"])


def _out(db: Session, c: Customer) -> CustomerOut:
    session_count = (
        db.scalar(
            select(func.count()).select_from(ChatSession).where(ChatSession.customer_id == c.id)
        )
        or 0
    )
    last = db.scalar(
        select(ChatSession.last_msg_at)
        .where(ChatSession.customer_id == c.id)
        .order_by(ChatSession.last_msg_at.desc())
        .limit(1)
    )
    return CustomerOut(
        id=c.id,
        name=c.name,
        industry=c.industry,
        stage=c.stage,
        owner_user_id=c.owner_user_id,
        health_score=c.health_score,
        health_level=c.health_level,
        session_count=int(session_count),
        last_msg_at=last,
    )


def _scoped_query(db: Session, identity: dict, q: str | None, stage: str | None):
    query = select(Customer)
    if identity["role"] == "sales":
        query = query.where(Customer.owner_user_id == identity["uid"])
    if q:
        query = query.where(Customer.name.contains(q))
    if stage:
        query = query.where(Customer.stage == stage)
    return query.order_by(Customer.id.desc())


@router.get("")
def list_customers(
    q: str | None = None,
    stage: str | None = None,
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    rows = db.scalars(_scoped_query(db, identity, q, stage)).all()
    return [_out(db, c) for c in rows]


@router.post("")
def create_customer(
    body: CustomerIn, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    c = Customer(
        name=body.name, industry=body.industry, stage=body.stage, owner_user_id=body.owner_user_id
    )
    db.add(c)
    db.commit()
    return _out(db, c)


@router.put("/{customer_id}")
def update_customer(
    customer_id: int,
    body: CustomerIn,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, "客户不存在")
    if identity["role"] == "sales" and c.owner_user_id != identity["uid"]:
        raise HTTPException(403, "仅可编辑自己负责的客户")
    c.name, c.industry, c.stage = body.name, body.industry, body.stage
    c.owner_user_id = body.owner_user_id
    db.commit()
    return _out(db, c)


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    identity: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_session),
):
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, "客户不存在")
    for s in db.scalars(select(ChatSession).where(ChatSession.customer_id == customer_id)).all():
        s.customer_id = None  # 会话回到待认领
    db.delete(c)
    db.commit()
    return {"deleted": customer_id}


@router.post("/{customer_id}/claim")
def claim(
    customer_id: int,
    body: ClaimIn,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    from ..services import mapping

    n = mapping.claim_sessions(db, customer_id, body.session_ids, identity["uid"])
    return {"claimed": n}


@router.get("/{customer_id}/export/csv")
def export_csv(
    customer_id: int,
    from_ts: str | None = Query(None),
    to_ts: str | None = Query(None),
    identity: dict = Depends(user_identity),
    db: Session = Depends(get_session),
):
    current_user(identity, db)
    sessions = db.scalars(select(ChatSession).where(ChatSession.customer_id == customer_id)).all()
    if identity["role"] == "sales" and not sessions:
        raise HTTPException(403, "无权访问该客户")
    from datetime import datetime

    f = datetime.fromisoformat(from_ts) if from_ts else None
    t = datetime.fromisoformat(to_ts) if to_ts else None
    filename, _buf = None, None
    parts = []
    for s in sessions:
        filename, buf = exporter.export_messages_csv(db, s.id, f, t, identity["uid"])
        parts.append(buf.getvalue())
    csv_text = "\n".join(parts)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename or 'export.csv'}"},
    )


@router.get("/owners")
def owners(identity: dict = Depends(user_identity), db: Session = Depends(get_session)):
    rows = db.scalars(select(AppUser).where(AppUser.role.in_(("admin", "manager", "sales")))).all()
    return [
        {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role}
        for u in rows
    ]
