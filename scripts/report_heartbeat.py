"""采集同步失败心跳：sync 脚本失败时上报 failed sync_task，触发采集异常红警。

用法（由 sync-wechat4.bat 在 errorlevel 分支调用，尽力而为、永不抛错）：
    python scripts/report_heartbeat.py --type incr_sync --note decrypt_failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector" / "src"))

from archcore_collector.config import CollectorSettings  # noqa: E402


def load_settings() -> CollectorSettings:
    import yaml

    path = Path("collector/config.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}
    return CollectorSettings(**data)


def main() -> int:
    parser = argparse.ArgumentParser(description="上报同步失败心跳")
    parser.add_argument("--type", default="incr_sync")
    parser.add_argument("--status", default="failed")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    try:
        import httpx

        settings = load_settings()
        httpx.post(
            f"{settings.server_base_url}/api/v1/ingest/sync-tasks",
            json={
                "type": args.type,
                "status": args.status,
                "stats": {"note": args.note},
                "log": args.note,
            },
            headers={
                "X-Collector-Token": settings.server_ingest_token,
                "X-Collector-Wxid": settings.collector_wxid,
            },
            timeout=10,
        )
        print(f"heartbeat {args.status} reported ({args.note})")
    except Exception as exc:  # 心跳失败静默：告警本身不能再失败
        print(f"heartbeat report failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
