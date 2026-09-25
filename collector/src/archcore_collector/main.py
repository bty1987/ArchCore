"""入口：archcore-collector [-c config.yaml] [--once]"""

from __future__ import annotations

import argparse
import logging

from .config import load_config


def run() -> None:
    parser = argparse.ArgumentParser(description="ArchCore 采集端")
    parser.add_argument("-c", "--config", default=None, help="配置文件路径（默认 ./config.yaml）")
    parser.add_argument("--once", action="store_true", help="执行一次增量同步后退出")
    parser.add_argument("--full", action="store_true", help="执行全量历史导入后退出")
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
            if args.full:
                print(run_full_import(settings, sender, state))
            else:
                print(run_incr_sync(settings, sender, state))
            # 冲刷历史积压（断链期间的 outbox 遗留批次）：无新消息时 submit 不会被调用
            print({"outbox_flushed": sender.flush()})
        finally:
            state.close()
        return

    from .scheduler import main_loop

    main_loop(settings)


if __name__ == "__main__":
    run()
