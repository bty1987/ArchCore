"""定时增量（F1-2）：只取各会话水位之后的新消息（小时级准实时）。"""

from __future__ import annotations

import logging
from datetime import datetime

from ..sources import build_source
from ..state import StateStore
from ..transform.normalize import normalize
from ..whitelist_sync import fetch_effective_whitelist, report_inventory

log = logging.getLogger(__name__)


def run_incr_sync(settings, sender, state: StateStore) -> dict:
    source = build_source(settings.source)
    flt = fetch_effective_whitelist(settings)
    stats = {"sessions": 0, "messages": 0, "filtered": 0}
    all_sessions = source.list_sessions()
    report_inventory(settings, all_sessions)
    for sess in all_sessions:
        if not flt.allow(sess.wx_id, sess.type, sess.name):
            stats["filtered"] += 1
            continue
        since_iso = state.get_watermark(sess.wx_id)
        since = datetime.fromisoformat(since_iso) if since_iso else None
        batch: list[dict] = []
        for raw in source.iter_messages(sess, since=since):
            msg = normalize(
                "decrypt",
                {
                    "session": {"wx_id": sess.wx_id, "type": sess.type, "name": sess.name},
                    "svr_id": raw.svr_id,
                    "sender_wxid": raw.sender_wxid,
                    "msg_type": raw.msg_type,
                    "content": raw.content,
                    "ts": raw.ts,
                    "recalled": raw.recalled,
                    "media_meta": raw.media_meta,
                    "raw": raw.raw,
                },
            )
            if msg is not None:
                batch.append(msg)
        if batch:
            result = sender.submit(batch)
            stats["messages"] += result["flushed"]
            last_ts = max(m["ts"] for m in batch)
            state.set_watermark(sess.wx_id, last_ts)
        stats["sessions"] += 1
    log.info("incr_sync done: %s", stats)
    return stats
