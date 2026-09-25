"""WAL 监听器（事件驱动实时同步，方案 2）。

监控微信 4.x 消息库/WAL 文件变化，有新消息立即触发「解密 + 采集」，
把消息进系统的延迟从 30 分钟压缩到分钟级。与 ArchCore-Sync 计划任务并存：
监听器负责实时性，计划任务兜底（监听器未运行时仍有 30 分钟同步）。

用法（建议登录时自启）：
    python scripts/watch_sync.py [--interval 20] [--min-gap 120]

实现：轮询 message_0.db / -wal 的 mtime（无第三方依赖）；
变化后调用 sync-wechat4.bat（解密 --force + 采集 --once），两次同步间强制冷却。
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

WATCH_FILES = ["message/message_0.db", "message/message_0.db-wal"]
COOLDOWN_SECONDS = 120


def last_mtime(root: Path) -> float:
    latest = 0.0
    for rel in WATCH_FILES:
        f = root / rel
        if f.exists():
            latest = max(latest, f.stat().st_mtime)
    return latest


def run_sync() -> None:
    bat = Path(__file__).resolve().parents[1] / "scripts" / "sync-wechat4.bat"
    subprocess.run([str(bat)], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="WAL 监听器：消息变化即触发同步")
    parser.add_argument("--data-root", default=r"D:\QMDownload\weixin\xwechat_files")
    parser.add_argument("--account", default=None, help="账号目录名（默认取最近活跃）")
    parser.add_argument("--interval", type=int, default=20, help="轮询间隔秒数")
    parser.add_argument("--min-gap", type=int, default=COOLDOWN_SECONDS,
                        help="两次同步最小间隔秒数")
    args = parser.parse_args()

    root = Path(args.data_root)
    account = (args.account or next(
        (d.name for d in sorted(root.iterdir(), key=lambda d: d.name)
         if (d / "db_storage" / "message").is_dir()), None))
    if not account:
        print("[watch] 未找到账号目录（先登录微信 4.x）")
        return 1
    msg_root = root / account / "db_storage"
    print(f"[watch] 监控 {msg_root}（每 {args.interval}s 轮询，冷却 {args.min_gap}s）")

    last_sync = 0.0
    last_mtime = 0.0
    while True:
        try:
            current = last_mtime(msg_root)
            now = time.time()
            if current > last_mtime and now - last_sync >= args.min_gap:
                print(f"[watch] {time.strftime('%H:%M:%S')} 检测到库变化，触发同步")
                run_sync()
                last_sync = time.time()
            last_mtime = max(last_mtime, current)
        except KeyboardInterrupt:
            print("[watch] 退出")
            return 0
        except Exception as exc:
            print(f"[watch] 轮询异常（继续）: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    import sys

    sys.exit(main())
