"""原始结构 → 标准消息（与 server /ingest 协议一致，schema_ver=1）。

注意：指纹由 server 端计算（设计决策 D8），collector 只透传 svr_id。
ts 统一输出 ISO 字符串（微信原始时间戳口径）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

MEDIA_TYPES = {"image", "video", "voice", "file"}


def normalize(source: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    """raw 需含：session(wx_id/type/name)、svr_id、sender_wxid、msg_type、
    content、ts(datetime 或 ISO 字符串)、recalled、media_meta。缺失 session/ts 返回 None。"""
    session = raw.get("session") or {}
    wx_id = session.get("wx_id")
    ts = raw.get("ts")
    if not wx_id or ts is None:
        return None
    ts_iso = ts if isinstance(ts, str) else ts.isoformat(sep=" ")

    msg_type = raw.get("msg_type", "text")
    media_meta = raw.get("media_meta")
    content = raw.get("content", "")
    if msg_type in MEDIA_TYPES and not content:
        # 媒体类存占位与摘要，不计入文本分析（PRD 3.3）
        name = (media_meta or {}).get("filename", "")
        content = f"[{msg_type}]{(' ' + name) if name else ''}"

    return {
        "session": {
            "wx_id": wx_id,
            "type": session.get("type", "group"),
            "name": session.get("name", ""),
        },
        "svr_id": str(raw["svr_id"]) if raw.get("svr_id") is not None else None,
        "sender_wxid": raw.get("sender_wxid"),
        "msg_type": msg_type,
        "content": content,
        "ts": ts_iso,
        "source": source,
        "recalled": bool(raw.get("recalled", False)),
        "media_meta": media_meta,
        "raw": raw.get("raw"),
    }


def to_batch(messages: list[dict]) -> dict:
    return {"schema_ver": 1, "messages": messages}


def now_iso() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")
