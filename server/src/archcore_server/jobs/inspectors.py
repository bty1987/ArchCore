"""巡检与调度入口：采集异常每 5 分钟；沉默/不活跃每日一次；聚合每 10 分钟；健康度每小时。"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from ..services import alert_engine

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
_session_factory = None


def run_collect_stale(factory) -> int:
    with factory() as db:
        n = alert_engine.collect_stale_inspection(db, datetime.utcnow())
        return n


def run_daily(factory) -> tuple[int, int]:
    with factory() as db:
        return (
            alert_engine.silence_inspection(db, datetime.utcnow()),
            alert_engine.inactive_inspection(db, datetime.utcnow()),
        )


def _job_aggregate() -> None:
    from . import aggregate

    aggregate.run(_session_factory)


def _job_collect_stale() -> None:
    run_collect_stale(_session_factory)


def _job_daily() -> None:
    n1, n2 = run_daily(_session_factory)
    log.info("daily inspect fired silence=%s inactive=%s", n1, n2)


def _job_health() -> None:
    from . import health

    health.run(_session_factory)


def _job_weekly_report() -> None:
    """每周一 09:00 生成经营周报并推送渠道;AI 未配置时留日志跳过。"""
    from ..services import notify as notify_svc
    from ..services import report as report_svc

    with _session_factory() as db:
        try:
            report = report_svc.generate_report(db, days=7)
        except ValueError as exc:
            log.info("weekly report skipped: %s", exc)
            return
        sent = notify_svc.dispatch_report(db, "ArchCore 经营周报(近 7 天)", report["content"])
        log.info("weekly report generated, pushed=%s", sent)


def start_jobs(factory) -> None:
    global _session_factory
    _session_factory = factory
    scheduler.add_job(_job_aggregate, "interval", minutes=10, id="aggregate")
    scheduler.add_job(_job_collect_stale, "interval", minutes=5, id="collect_stale")
    scheduler.add_job(_job_daily, "cron", hour=8, minute=30, id="daily_inspect")
    scheduler.add_job(_job_health, "interval", hours=1, id="health")
    scheduler.add_job(
        _job_weekly_report, "cron", day_of_week="mon", hour=9, minute=0, id="weekly_report"
    )
    scheduler.start()
    log.info("jobs started")


def stop_jobs() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
