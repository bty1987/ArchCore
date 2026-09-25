"""消息：组合检索（keyset 分页）+ 上下文 + 媒体鉴权下发。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import current_user, get_identity
from ..schemas import MessageOut, MessageTagIn
from ..services import analysis
from .deps import get_session, user_identity

router = APIRouter(tags=["messages"])


def _to_out(row: dict) -> MessageOut:
    import json

    media_meta = row["media_meta"]
    if isinstance(media_meta, str):  # 原生 SQL 行返回的是 JSON 文本
        media_meta = json.loads(media_meta) if media_meta not in ("", "null") else None
    return MessageOut(
        id=row["id"],
        session_id=row["session_id"],
        svr_id=row.get("svr_id"),
        sender_wxid=row["sender_wxid"],
        sender_type=row["sender_type"],
        msg_type=row["msg_type"],
        content=row["content"],
        media_meta=media_meta,
        tags=row.get("tags", []),
        ts=datetime.fromisoformat(row["ts"]),
        recalled=bool(row["recalled"]),
        source=row["source"],
    )


@router.get("/messages")
def search(
    session_id: int | None = None,
    q: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    sender_type: str | None = None,
    sender_wxid: str | None = None,
    msg_type: str | None = None,
    customer_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(50, le=200),
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    current_user(identity, db)
    rows, next_cursor = analysis.search_messages(
        db,
        session_id=session_id,
        q=q,
        from_ts=from_ts,
        to_ts=to_ts,
        sender_type=sender_type,
        sender_wxid=sender_wxid,
        msg_type=msg_type,
        customer_id=customer_id,
        cursor=cursor,
        limit=limit,
        identity_role=identity["role"],
        identity_uid=identity["uid"],
    )
    rows = analysis.attach_tags(db, rows)
    return {"items": [_to_out(r) for r in rows], "next_cursor": next_cursor}


@router.get("/messages/{message_id}/context")
def context(
    message_id: int,
    before: int = Query(20, le=100),
    after: int = Query(20, le=100),
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    current_user(identity, db)
    rows = analysis.message_context(db, message_id, before, after)
    if rows is None:
        raise HTTPException(404, "消息不存在")
    return [_out_model(m) for m in rows]


def _out_model(m):
    return MessageOut.model_validate(m)


@router.get("/messages/{message_id}/tags")
def list_message_tags(
    message_id: int, identity: dict = Depends(get_identity), db: Session = Depends(get_session)
):
    from sqlalchemy import select

    from ..models import MessageTag

    current_user(identity, db)
    rows = db.scalars(
        select(MessageTag).where(MessageTag.message_id == message_id).order_by(MessageTag.id)
    ).all()
    return [t.tag for t in rows]


@router.post("/messages/{message_id}/tags")
def add_message_tag(
    message_id: int,
    body: MessageTagIn,
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    from sqlalchemy import select

    from ..models import MessageTag

    current_user(identity, db)
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(422, "tag 不能为空")
    exists = db.scalar(
        select(MessageTag).where(MessageTag.message_id == message_id, MessageTag.tag == tag)
    )
    if exists is None:
        db.add(MessageTag(message_id=message_id, tag=tag, created_by=identity["uid"]))
        db.commit()
    rows = db.scalars(
        select(MessageTag).where(MessageTag.message_id == message_id).order_by(MessageTag.id)
    ).all()
    return {"message_id": message_id, "tags": [t.tag for t in rows]}


@router.delete("/messages/{message_id}/tags/{tag}")
def delete_message_tag(
    message_id: int,
    tag: str,
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    from sqlalchemy import delete, select

    from ..models import MessageTag

    current_user(identity, db)
    db.execute(delete(MessageTag).where(MessageTag.message_id == message_id, MessageTag.tag == tag))
    db.commit()
    rows = db.scalars(
        select(MessageTag).where(MessageTag.message_id == message_id).order_by(MessageTag.id)
    ).all()
    return {"message_id": message_id, "tags": [t.tag for t in rows]}


@router.get("/media/{path:path}")
def media(path: str, identity: dict = Depends(user_identity), db: Session = Depends(get_session)):
    current_user(identity, db)
    root = Path(get_settings().media_dir).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "媒体不存在")
    return FileResponse(target)
