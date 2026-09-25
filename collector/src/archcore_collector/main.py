"""入口：archcore-collector [-c config.yaml] [--once]"""

from __future__ import annotations

import argparse
import logging
import time

from .config import load_config


def _report_sync_task(settings, task_type: str, stats: dict, ok: bool, log_text: str = "") -> None:
    """同步结果上报（采集管理页的心跳数据源）；上报失败不影响采集本身。"""
    import httpx

    try:
        httpx.post(
            f"{settings.server_base_url}/api/v1/ingest/sync-tasks",
            json={
                "type": task_type,
                "status": "success" if ok else "failed",
                "stats": stats,
                "log": log_text,
            },
            headers={
                "X-Collector-Token": settings.server_ingest_token,
                "X-Collector-Wxid": settings.collector_wxid,
            },
            timeout=10,
        )
    except httpx.HTTPError:
        pass


def run() -> None:
    parser = argparse.ArgumentParser(description="ArchCore 采集端")
    parser.add_argument("-c", "--config", default=None, help="配置文件路径（默认 ./config.yaml）")
    parser.add_argument("--once", action="store_true", help="执行一次增量同步后退出")
    parser.add_argument("--full", action="store_true", help="执行全量历史导入后退出")
    parser.add_argument("--padlocal", action="store_true",
                        help="前台运行 PadLocal 实时桥接监护器（需配置 padlocal.token）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_config(args.config)

    if args.once or args.full:
        import httpx

        from .decrypt_worker.full_import import run_full_import
        from .decrypt_worker.incr_sync import run_incr_sync
        from .sender import Sender
        from .state import StateStore

        state = StateStore(settings.state_db)
        try:
            sender = Sender(httpx.Client(), settings, state)
            task_type = "full_import" if args.full else "incr_sync"
            try:
                stats = (
                    run_full_import(settings, sender, state)
                    if args.full
                    else run_incr_sync(settings, sender, state)
                )
                print(stats)
                _report_sync_task(settings, task_type, stats, ok=True)
            except Exception as exc:  # 任务失败也要留心跳记录，供采集异常巡检发现
                print(f"task failed: {exc}")
                _report_sync_task(settings, task_type, {"error": str(exc)}, ok=False)
                raise
            # 冲刷历史积压（断链期间的 outbox 遗留批次）：无新消息时 submit 不会被调用
            print({"outbox_flushed": sender.flush()})
        finally:
            state.close()
        return

    if args.padlocal:
        from .padlocal_worker import PadlocalSupervisor

        sup = PadlocalSupervisor(settings)
        if not sup.start():
            return
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sup.stop()
        return

    from .scheduler import main_loop

    main_loop(settings)


if __name__ == "__main__":
    run()
