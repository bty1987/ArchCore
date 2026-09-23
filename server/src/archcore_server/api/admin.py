"""管理：用户 / 内部成员名单 / 词库 / 设置 / 审计日志。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import hash_password
from ..models import AppSetting, AppUser, AuditLog, Keyword, Member
from ..schemas import KeywordIn, MemberIn, SettingIn, UserIn
from .deps import admin_identity, get_session, manager_identity

router = APIRouter(tags=["admin"])


# ---------- 用户 ----------


@router.get("/users")
def list_users(identity: dict = Depends(admin_identity), db: Session = Depends(get_session)):
    rows = db.scalars(select(AppUser)).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "enabled": u.enabled,
        }
        for u in rows
    ]


@router.post("/users")
def create_user(
    body: UserIn, identity: dict = Depends(admin_identity), db: Session = Depends(get_session)
):
    if not body.password:
        raise HTTPException(422, "新建用户必须提供密码")
    if body.role not in ("admin", "manager", "sales"):
        raise HTTPException(422, "role 无效")
    if db.scalar(select(AppUser).where(AppUser.username == body.username)):
        raise HTTPException(409, "用户名已存在")
    u = AppUser(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        enabled=body.enabled,
    )
    db.add(u)
    db.commit()
    return {"id": u.id}


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserIn,
    identity: dict = Depends(admin_identity),
    db: Session = Depends(get_session),
):
    u = db.get(AppUser, user_id)
    if u is None:
        raise HTTPException(404, "用户不存在")
    u.display_name, u.role, u.enabled = body.display_name, body.role, body.enabled
    if body.password:
        u.password_hash = hash_password(body.password)
    db.commit()
    return {"id": u.id}


# ---------- 内部成员名单 ----------


@router.get("/members")
def list_members(identity: dict = Depends(manager_identity), db: Session = Depends(get_session)):
    return db.scalars(select(Member)).all()


@router.post("/members")
def create_member(
    body: MemberIn, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    if body.match_type not in ("wxid", "nickname", "remark"):
        raise HTTPException(422, "match_type 无效")
    exists = db.scalar(
        select(Member).where(
            Member.match_type == body.match_type, Member.match_value == body.match_value
        )
    )
    if exists:
        raise HTTPException(409, "成员已存在")
    m = Member(
        match_type=body.match_type, match_value=body.match_value, display_name=body.display_name
    )
    db.add(m)
    db.commit()
    return {"id": m.id}


@router.delete("/members/{member_id}")
def delete_member(
    member_id: int, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    m = db.get(Member, member_id)
    if m:
        db.delete(m)
        db.commit()
    return {"deleted": member_id}


# ---------- 词库 ----------


@router.get("/keywords")
def list_keywords(
    category: str | None = None,
    identity: dict = Depends(manager_identity),
    db: Session = Depends(get_session),
):
    query = select(Keyword)
    if category:
        query = query.where(Keyword.category == category)
    return db.scalars(query).all()


@router.post("/keywords")
def create_keyword(
    body: KeywordIn, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    if body.category not in ("risk", "focus"):
        raise HTTPException(422, "category 须为 risk/focus")
    exists = db.scalar(
        select(Keyword).where(Keyword.category == body.category, Keyword.word == body.word)
    )
    if exists:
        raise HTTPException(409, "词条已存在")
    k = Keyword(category=body.category, word=body.word, enabled=body.enabled)
    db.add(k)
    db.commit()
    return {"id": k.id}


@router.delete("/keywords/{keyword_id}")
def delete_keyword(
    keyword_id: int, identity: dict = Depends(manager_identity), db: Session = Depends(get_session)
):
    k = db.get(Keyword, keyword_id)
    if k:
        db.delete(k)
        db.commit()
    return {"deleted": keyword_id}


# ---------- 设置 ----------


@router.get("/settings")
def get_settings_all(identity: dict = Depends(admin_identity), db: Session = Depends(get_session)):
    return {r.key: r.value for r in db.scalars(select(AppSetting)).all()}


@router.put("/settings")
def put_setting(
    body: SettingIn, identity: dict = Depends(admin_identity), db: Session = Depends(get_session)
):
    row = db.get(AppSetting, body.key)
    if row is None:
        row = AppSetting(key=body.key)
    row.value = body.value
    db.add(row)
    db.commit()
    return {row.key: row.value}


# ---------- 审计日志 ----------


@router.get("/audit-logs")
def list_audit(
    identity: dict = Depends(admin_identity),
    db: Session = Depends(get_session),
    limit: int = Query(100, le=500),
):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "action": a.action,
            "target": a.target,
            "detail": a.detail,
            "created_at": a.created_at,
        }
        for a in rows
    ]
