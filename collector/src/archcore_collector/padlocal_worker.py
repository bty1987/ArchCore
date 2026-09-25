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


class BridgeSupervisor:
    """通用 Node 桥接监护器：崩溃指数退避重启。mode: padlocal / wcferry。"""

    def __init__(self, settings, mode: str = "padlocal"):
        self.settings = settings
        self.mode = mode
        self.proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _cfg(self):
        return self.settings.padlocal if self.mode == "padlocal" else self.settings.wcferry

    def start(self) -> bool:
        cfg = self._cfg()
        if not cfg.enabled:
            log.info("%s 实时轨未启用", self.mode)
            return False
        if self.mode == "padlocal" and not cfg.token:
            log.info("padlocal 未配置 token，不启动")
            return False
        bridge = Path(cfg.bridge)
        if not bridge.is_file():
            log.warning("桥接脚本不存在：%s（实时轨不启动）", bridge)
            return False
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=f"{self.mode}-supervisor")
        self._thread.start()
        return True

    def _loop(self) -> None:
        cfg = self._cfg()
        backoff = 5
        while not self._stop.is_set():
            cmd = [
                cfg.node, str(bridge_path(cfg)),
                "--mode", (cfg.mode if self.mode == "padlocal" else self.mode),
                "--token", getattr(cfg, "token", ""),
                "--server", self.settings.server_base_url,
                "--collector-token", self.settings.server_ingest_token,
                "--bridge-name", f"archcore-{self.mode}",
            ]
            if self.mode == "padlocal":
                if cfg.endpoint:
                    cmd += ["--endpoint", cfg.endpoint]
                if cfg.authority:
                    cmd += ["--authority", cfg.authority]
                if cfg.no_tls:
                    cmd.append("--no-tls")
            if cfg.allow_dm:
                cmd.append("--allow-dm")
            log.info("%s 桥接启动", self.mode)
            try:
                self.proc = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[3])
                code = self.proc.wait()
                log.warning("%s 桥接退出（code=%s），%ss 后重启", self.mode, code, backoff)
            except (OSError, subprocess.SubprocessError) as exc:
                log.error("%s 桥接异常：%s，%ss 后重启", self.mode, exc, backoff)
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


class PadlocalSupervisor(BridgeSupervisor):
    def __init__(self, settings):
        super().__init__(settings, "padlocal")


class WcferrySupervisor(BridgeSupervisor):
    def __init__(self, settings):
        super().__init__(settings, "wcferry")

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
