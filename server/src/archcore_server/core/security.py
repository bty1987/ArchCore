"""认证与 RBAC：pbkdf2 口令哈希（stdlib）+ JWT（8h）+ 角色依赖。

角色：admin（全部）、manager（业务管理）、sales（仅自己负责的客户）。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)
PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: int, role: str, settings: Settings) -> str:
    payload = {
        "uid": user_id,
        "role": role,
        "exp": int(time.time()) + settings.jwt_ttl_hours * 3600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 无效或已过期") from exc


def get_identity(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict[str, Any]:
    """返回身份上下文 {"uid", "role"}。"""
    settings = get_settings()
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未认证")
    return decode_token(creds.credentials, settings)


def require_roles(*roles: str):
    def _dep(identity: dict[str, Any] = Depends(get_identity)) -> dict[str, Any]:
        if identity["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return identity

    return _dep


def current_user(identity: dict[str, Any], db: Session):
    from ..models import AppUser

    user = db.scalar(select(AppUser).where(AppUser.id == identity["uid"]))
    if user is None or not user.enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在或已停用")
    return user
