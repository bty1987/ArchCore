"""认证：POST /auth/login · GET /auth/me。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import create_token, current_user, get_identity, hash_password, verify_password
from ..models import AppUser
from ..schemas import LoginIn, MeOut, TokenOut
from .deps import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_session)):
    user = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if user is None or not user.enabled or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    token = create_token(user.id, user.role, _settings())
    return TokenOut(token=token, role=user.role, display_name=user.display_name or user.username)


def _settings():
    from ..core.config import get_settings

    return get_settings()


@router.get("/me", response_model=MeOut)
def me(identity: dict = Depends(get_identity), db: Session = Depends(get_session)):
    user = current_user(identity, db)
    return MeOut(id=user.id, username=user.username, display_name=user.display_name, role=user.role)


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
