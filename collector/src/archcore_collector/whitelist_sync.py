"""白名单服务端化：采集端每轮同步前拉取生效配置，并上报发现的会话清单。

服务端不可达时回退本地 config.yaml 的白名单（保证离线可用）；
page 操作（管理台白名单页）由此即时作用于下一轮采集。
"""

from __future__ import annotations

import logging

import httpx

from .sources import SessionInfo
from .transform.filter import WhitelistFilter

log = logging.getLogger(__name__)


def fetch_effective_whitelist(settings) -> WhitelistFilter:
    """服务端白名单优先；失败回退本地配置。"""
    try:
        resp = httpx.get(
            f"{settings.server_base_url}/api/v1/ingest/whitelist",
            headers={"X-Collector-Token": settings.server_ingest_token},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("拉取服务端白名单失败，回退本地配置：%s", exc)
        return WhitelistFilter(settings.whitelist)

    # 服务端从未配置（无规则且未开 allow_all）视为「未接管」，回退本地配置——
    # 新部署零配置可用；管理台一旦配置即以服务端为准。
    if not data.get("allow_all") and not data.get("groups"):
        log.info("服务端白名单未配置，使用本地 config.yaml 白名单")
        return WhitelistFilter(settings.whitelist)

    from .config import WhitelistConfig

    cfg = WhitelistConfig(
        allow_all=bool(data.get("allow_all")),
        groups=list(data.get("groups") or []),
        group_name_patterns=settings.whitelist.group_name_patterns,
        allow_dm=settings.whitelist.allow_dm,
    )
    log.info("白名单已从服务端拉取：allow_all=%s groups=%s", cfg.allow_all, len(cfg.groups))
    return WhitelistFilter(cfg)


def report_inventory(settings, sessions: list[SessionInfo]) -> None:
    """上报发现的会话清单（含无消息的群），尽力而为不阻断采集。"""
    if not sessions:
        return
    try:
        httpx.post(
            f"{settings.server_base_url}/api/v1/ingest/sessions",
            json={
                "sessions": [{"wx_id": s.wx_id, "type": s.type, "name": s.name} for s in sessions]
            },
            headers={"X-Collector-Token": settings.server_ingest_token},
            timeout=10,
        )
        log.info("会话清单已上报：%s 个", len(sessions))
    except httpx.HTTPError as exc:
        log.warning("会话清单上报失败（不影响采集）：%s", exc)
