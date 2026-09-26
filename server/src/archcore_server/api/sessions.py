"""会话：待认领列表 / 映射 / 解除映射。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.security import get_identity
from ..models import ChatSession, Customer
from ..schemas import SessionMapIn, SessionOut
from ..services import mapping
from .deps import get_session, manager_identity

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def list_sessions(
    claimed: bool | None = None,
    type: str | None = None,
    customer_id: int | None = None,
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    query = select(ChatSession).where(ChatSession.status == "active")
    if claimed is False:
        query = query.where(ChatSession.customer_id.is_(None))
    elif claimed is True:
        query = query.where(ChatSession.customer_id.is_not(None))
    if customer_id is not None:
        query = query.where(ChatSession.customer_id == customer_id)
    if type:
        query = query.where(ChatSession.type == type)
    if identity["role"] == "sales":
        query = query.where(
            ChatSession.customer_id.in_(
                select(Customer.id).where(Customer.owner_user_id == identity["uid"])
            )
        )
    rows = db.scalars(query.order_by(ChatSession.last_msg_at.desc())).all()
    out = []
    for s in rows:
        count = (
            db.scalar(select(func.count()).select_from(_msg()).where(_msg().session_id == s.id))
            or 0
        )
        cname = None
        if s.customer_id:
            c = db.get(Customer, s.customer_id)
            cname = c.name if c else None
        out.append(
            SessionOut(
                id=s.id,
                wx_id=s.wx_id,
                type=s.type,
                name=s.name,
                customer_id=s.customer_id,
                customer_name=cname,
                last_msg_at=s.last_msg_at,
                status=s.status,
                message_count=int(count),
            )
        )
    return out


def _msg():
    from ..models import Message

    return Message


@router.post("/{session_id}/map")
def map_session(
    session_id: int,
    body: SessionMapIn,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    try:
        s = mapping.map_session(db, session_id, body.customer_id, identity["uid"])
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return SessionOut(
        id=s.id,
        wx_id=s.wx_id,
        type=s.type,
        name=s.name,
        customer_id=s.customer_id,
        last_msg_at=s.last_msg_at,
        status=s.status,
    )


@router.get("/unclaimed")
def unclaimed(identity: dict = Depends(manager_identity), db: Session = Depends(get_session)):
    return mapping.list_unclaimed(db)


@router.get("/{session_id}/export/csv")
def export_session_csv(
    session_id: int,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    """单会话导出 CSV（全量审计，见 exporter）。"""
    from ..services import exporter

    filename, buf = exporter.export_messages_csv(db, session_id, None, None, identity["uid"])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
