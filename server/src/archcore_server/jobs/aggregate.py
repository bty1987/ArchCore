"""日聚合任务：message_daily 增量重算（D7：分析不扫明细）。"""

from __future__ import annotations

import logging

from ..services import analysis

log = logging.getLogger(__name__)


def run(factory) -> int:
    with factory() as db:
        n = analysis.recompute_daily(db, days=3)
        log.info("aggregate done sessions=%s", n)
        return n
