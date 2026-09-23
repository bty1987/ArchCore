"""实时轨（F1-3，可选增强，可整体摘除）：WCF 回调 → 标准化 → outbox。

⚠️ 依赖 M0 验证通过（微信 3.9.12 可登录 + 32 位匹配）。wcf_enabled=false 或
wcferry 未安装时不加载，系统回退为解密轨小时级准实时（降级预案）。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

log = logging.getLogger(__name__)


class WcfWorker:
    """独立线程消费 WCF 消息回调；任何启动失败仅记录日志，不影响主轨。"""

    def __init__(self, settings, state):
        self.settings = settings
        self.state = state
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        if not self.settings.wcf_enabled:
            log.info("wcf_worker 未启用（wcf_enabled=false）")
            return False
        import importlib.util

        if importlib.util.find_spec("wcferry") is None:
            log.warning("wcferry 未安装，实时轨不启用（F1-3 依赖 M0 验证）")
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="wcf-worker")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        from wcferry import Wcf

        wcf = Wcf()
        log.info("wcf_worker 已连接，微信 %s", wcf.get_self_wxid())
        while not self._stop.is_set():
            msgs = wcf.get_msg()
            for m in msgs:
                self._handle(wcf, m)
        wcf.cleanup()

    def _handle(self, wcf, m) -> None:
        """WCF WxMsg → 原始结构 → outbox（经白名单过滤）。"""
        from .transform.filter import WhitelistFilter
        from .transform.normalize import normalize

        flt = WhitelistFilter(self.settings.whitelist)
        is_group = m.from_group()
        wx_id = m.roomid if is_group else m.sender
        session_type = "group" if is_group else "dm"
        name = ""  # 群名快照以解密轨为准；实时轨按 wx_id 白名单过滤
        if not flt.allow(wx_id, session_type, name):
            return
        msg = normalize(
            "wcf",
            {
                "session": {"wx_id": wx_id, "type": session_type, "name": name},
                "svr_id": str(m.id) if m.id else None,
                "sender_wxid": m.sender,
                "msg_type": "text",
                "content": m.content or "",
                "ts": datetime.now(),  # WCF 回调时间仅参考；解密轨 ts 为准
                "raw": {"wcf": {"type": m.type, "is_self": m.is_self}},
            },
        )
        if msg is not None:
            import json

            from .transform.normalize import to_batch

            self.state.enqueue(json.dumps(to_batch([msg]), ensure_ascii=False))
