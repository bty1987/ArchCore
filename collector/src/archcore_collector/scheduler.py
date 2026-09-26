"""调度入口：APScheduler 常驻（增量 + outbox 冲刷）。"""

from __future__ import annotations

import logging

import httpx

from .decrypt_worker.incr_sync import run_incr_sync
from .sender import Sender
from .state import StateStore

log = logging.getLogger(__name__)


def run_once(settings) -> dict:
    """单次增量同步（测试与手动触发入口）。"""
    state = StateStore(settings.state_db)
    try:
        sender = Sender(httpx.Client(), settings, state)
        return run_incr_sync(settings, sender, state)
    finally:
        state.close()


def main_loop(settings) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    state = StateStore(settings.state_db)
    sender = Sender(httpx.Client(), settings, state)
    sched = BlockingScheduler()

    sched.add_job(
        lambda: run_incr_sync(settings, sender, state),
        "interval",
        minutes=settings.schedule.incr_minutes,
        id="incr_sync",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(sender.flush, "interval", seconds=settings.schedule.flush_seconds, id="flush")

    supervisors = []
    if settings.padlocal.enabled and settings.padlocal.token:
        from .padlocal_worker import PadlocalSupervisor

        pad_sup = PadlocalSupervisor(settings)
        if pad_sup.start():
            supervisors.append(pad_sup)
            log.info("padlocal 实时轨已并行启动（秒级），解密轨 %s 分钟/次兜底",
                     settings.schedule.incr_minutes)

    log.info(
        "collector 启动：增量 %s 分钟/次，冲刷 %s 秒/次",
        settings.schedule.incr_minutes,
        settings.schedule.flush_seconds,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        for sup in supervisors:
            sup.stop()
        state.close()
