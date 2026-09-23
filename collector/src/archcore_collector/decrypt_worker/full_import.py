"""全量历史导入（F1-1）：白名单会话逐一拉取 → 标准化 → 上报 → 记水位。

失败重跑安全：消息以 svr_id 幂等入库，重跑只产生 skipped。
"""

from __future__ import annotations

import logging

from ..sources import build_source
from ..state import StateStore
from ..transform.filter import WhitelistFilter
from ..transform.normalize import normalize

log = logging.getLogger(__name__)


def run_full_import(settings, sender, state: StateStore) -> dict:
    source = build_source(settings.source)
    flt = WhitelistFilter(settings.whitelist)
    stats = {"sessions": 0, "messages": 0, "filtered": 0}
    for sess in source.list_sessions():
        if not flt.allow(sess.wx_id, sess.type, sess.name):
            stats["filtered"] += 1
            continue
        batch: list[dict] = []
        for raw in source.iter_messages(sess):
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
    log.info("full_import done: %s", stats)
    return stats
