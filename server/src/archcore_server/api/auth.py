"""认证:POST /auth/login · GET /auth/me · POST /auth/change-password。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import create_token, current_user, get_identity, hash_password, verify_password
from ..models import AppUser
from ..schemas import ChangePasswordIn, LoginIn, MeOut, TokenOut
from .deps import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

# 首启改密判定候选:bootstrap 密码 + 历史默认值(差距分析 P0 #9)
_DEFAULT_PASSWORD_CANDIDATES = ("admin123456", "admin123")


def _is_default_password(user: AppUser, bootstrap_password: str) -> bool:
    if user.username != "admin":
        return False
    for candidate in dict.fromkeys((bootstrap_password, *_DEFAULT_PASSWORD_CANDIDATES)):
        if verify_password(candidate, user.password_hash):
            return True
    return False


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_session)):
    user = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if user is None or not user.enabled or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    settings = _settings()
    token = create_token(user.id, user.role, settings)
    return TokenOut(
        token=token,
        role=user.role,
        display_name=user.display_name or user.username,
        must_change_password=_is_default_password(user, settings.admin_bootstrap_password),
    )


def _settings():
    from ..core.config import get_settings

    return get_settings()


@router.get("/me", response_model=MeOut)
def me(identity: dict = Depends(get_identity), db: Session = Depends(get_session)):
    user = current_user(identity, db)
    return MeOut(id=user.id, username=user.username, display_name=user.display_name, role=user.role)


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    identity: dict = Depends(get_identity),
    db: Session = Depends(get_session),
):
    """当前登录用户修改自己的密码;成功后须重新登录。"""
    user = current_user(identity, db)
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "旧密码错误")
    if body.old_password == body.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与旧密码相同")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True, "message": "密码已更新,请重新登录"}


def bootstrap_admin(db: Session, password: str) -> None:
    if db.scalar(select(AppUser).limit(1)) is None:
        db.add(
            AppUser(
                username="admin",
                password_hash=hash_password(password),
                display_name="管理员",
                role="admin",
            )
        )
        db.commit()
