"""公共依赖：DB 会话、身份、采集端 token 校验、审计。"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import require_roles
from ..models import AuditLog


def get_session(request: Request) -> Session:
    s = request.app.state.session_factory()
    try:
        yield s
    finally:
        s.close()


def require_collector_token(x_collector_token: str = Header(default="")) -> None:
    if not x_collector_token or x_collector_token != get_settings().collector_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "采集端 token 无效")


def scope_sales(identity: dict[str, Any]):
    """sales 角色数据边界：返回 owner 过滤值（None 表示不过滤）。"""
    return identity["uid"] if identity["role"] == "sales" else None


def audit(
    db: Session,
    identity: dict[str, Any] | None,
    action: str,
    target: str = "",
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=identity["uid"] if identity else None,
            action=action,
            target=target,
            detail=detail or {},
        )
    )


def admin_identity(identity: dict[str, Any] = Depends(require_roles("admin"))) -> dict[str, Any]:
    return identity


def manager_identity(
    identity: dict[str, Any] = Depends(require_roles("admin", "manager")),
) -> dict[str, Any]:
    return identity


def user_identity(
    identity: dict[str, Any] = Depends(require_roles("admin", "manager", "sales")),
) -> dict[str, Any]:
    return identity
