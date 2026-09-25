"""会话白名单过滤（F1-6，合规边界）。

在 transform 阶段执行：非白名单会话的消息在此被丢弃，
数据不进入上报通道与本地暂存队列——即不出微信数据目录。
"""

from __future__ import annotations

import re

from ..config import WhitelistConfig


class WhitelistFilter:
    def __init__(self, cfg: WhitelistConfig):
        self.cfg = cfg
        self._patterns = [re.compile(p) for p in cfg.group_name_patterns]

    def allow(self, wx_id: str, session_type: str, name: str) -> bool:
        if self.cfg.allow_all:
            return True
        if session_type == "group":
            if wx_id in self.cfg.groups:
                return True
            return bool(name and any(p.search(name) for p in self._patterns))
        if session_type == "dm":
            return self.cfg.allow_dm
        return False
