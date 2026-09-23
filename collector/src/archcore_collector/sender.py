"""批量上报：500 条/批、失败重试（指数退避）、本地暂存（state.outbox）。

依赖注入 httpx.Client 便于测试（ASGITransport 打进程内 server）。
"""

from __future__ import annotations

import json
import logging

import httpx

from .state import StateStore

log = logging.getLogger(__name__)

BATCH_LIMIT = 500


class Sender:
    def __init__(self, client: httpx.Client, settings, state: StateStore):
        self.client = client
        self.settings = settings
        self.state = state

    def submit(self, messages: list[dict]) -> dict:
        """标准化消息入 outbox 并立即冲刷；返回本次确认的 {enqueued, flushed}。"""
        from .transform.normalize import to_batch

        enqueued = 0
        for i in range(0, len(messages), BATCH_LIMIT):
            batch = to_batch(messages[i : i + BATCH_LIMIT])
            self.state.enqueue(json.dumps(batch, ensure_ascii=False, default=str))
            enqueued += len(batch["messages"])
        flushed = self.flush()
        return {"enqueued": enqueued, "flushed": flushed}

    def flush(self) -> int:
        """冲刷 outbox：取 pending 批次上报，2xx 标 sent，失败退避重试。返回确认条数。"""
        confirmed = 0
        while True:
            rows = self.state.take_pending(1)  # 单批循环取，保证顺序
            if not rows:
                break
            row_id, payload = rows[0]
            batch = json.loads(payload)
            count = len(batch.get("messages", []))
            try:
                resp = self.client.post(
                    f"{self.settings.server_base_url}/api/v1/ingest/messages",
                    json=batch,
                    headers={"X-Collector-Token": self.settings.server_ingest_token},
                    timeout=30,
                )
                if resp.status_code == 200:
                    self.state.mark_sent([row_id])
                    confirmed += count
                else:
                    self._retry(row_id, resp.text)
                    break
            except httpx.HTTPError as exc:
                self._retry(row_id, str(exc))
                break
        return confirmed

    def _retry(self, row_id: int, error: str) -> None:
        log.warning("ingest 批次 %s 上报失败，退避重试: %s", row_id, error[:200])
        attempts = self._attempts(row_id) + 1
        self.state.mark_retry([row_id], {row_id: attempts})

    def _attempts(self, row_id: int) -> int:
        row = self.state.conn.execute(
            "SELECT attempts FROM outbox WHERE id = ?", (row_id,)
        ).fetchone()
        return row[0] if row else 0
