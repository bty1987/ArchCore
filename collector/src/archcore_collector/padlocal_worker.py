"""PadLocal 实时轨监护器：拉起 Node 桥接进程，崩溃自动重启（指数退避）。

独立于解密轨运行：主循环（APScheduler）与 PadLocal 桥可并行——
解密轨小时级兜底，PadLocal 秒级实时，svr_id 去重保证双轨并存不重复。
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)



class PadlocalSupervisor:
    def __init__(self, settings):
        self.cfg = settings.padlocal
        self.proc = None
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> bool:
        if not (self.cfg.enabled and self.cfg.token):
            log.info("padlocal 未启用（enabled/token 未配置）")
            return False
        bridge = Path(self.cfg.bridge)
        if not bridge.is_file():
            log.warning("桥接脚本不存在：%s（实时轨不启动）", bridge)
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="padlocal-supervisor")
        self._thread.start()
        return True

    def _loop(self) -> None:
        backoff = 5
        while not self._stop.is_set():
            cmd = [
                self.cfg.node, str(bridge_path(self.cfg)),
                "--mode", self.cfg.mode,
                "--token", self.cfg.token,
                "--server", self.settings.server_base_url,
                "--collector-token", self.settings.server_ingest_token,
                "--bridge-name", "archcore-padlocal",
            ]
            if self.cfg.endpoint:
                cmd += ["--endpoint", self.cfg.endpoint]
            if self.cfg.authority:
                cmd += ["--authority", self.cfg.authority]
            if self.cfg.no_tls:
                cmd.append("--no-tls")
            if self.cfg.allow_dm:
                cmd.append("--allow-dm")
            log.info("padlocal 桥接启动")
            try:
                self.proc = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[3])
                code = self.proc.wait()
                log.warning("padlocal 桥接退出（code=%s），%ss 后重启", code, backoff)
            except (OSError, subprocess.SubprocessError) as exc:
                log.error("padlocal 桥接异常：%s，%ss 后重启", exc, backoff)
                code = -1
            for _ in range(backoff * 2):
                if self._stop.is_set():
                    return
                time.sleep(0.5)
            backoff = min(300, backoff * 2)

    def stop(self) -> None:
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def bridge_path(cfg) -> Path:
    return Path(cfg.bridge).resolve()


def run_supervisor_sync(settings) -> None:
    """前台运行监护器（--padlocal 独立模式）。"""
    sup = PadlocalSupervisor(settings)
    if not sup.start():
        return
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sup.stop()
