"""一键备份：SQLite 数据库（在线 backup API，保证一致性）+ media/ + config.yaml。

用法：python deploy/backup.py --db ./data/archcore.db --media ./data/media \
        --config ./collector/config.yaml --out ./backups
备份目录本身须按运维规划 2.4 加密保管/内网异地双份，禁止上传公有云盘。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="ArchCore 一键备份")
    parser.add_argument("--db", default="./data/archcore.db")
    parser.add_argument("--media", default="./data/media")
    parser.add_argument("--config", default="collector/config.yaml")
    parser.add_argument("--plain", default="./data/wechat4_plain",
                        help="微信 4.x 解密明文库（数据的第二副本，一并备份）")
    parser.add_argument("--out", default="./backups")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = Path(args.out) / stamp
    dest.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db)
    if db_path.exists():
        target = dest / "archcore.db"
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(target))
        with dst:
            src.backup(dst)  # 在线备份：WAL 模式下也能拿到一致性快照
        dst.close()
        src.close()
        print(f"✓ 数据库 → {target}")
    else:
        print(f"⚠ 数据库不存在：{db_path}")

    media = Path(args.media)
    if media.exists():
        shutil.copytree(media, dest / "media", dirs_exist_ok=True)
        print(f"✓ 媒体目录 → {dest / 'media'}")

    plain = Path(args.plain)
    if plain.exists():
        shutil.copytree(plain, dest / "wechat4_plain", dirs_exist_ok=True)
        print(f"✓ 解密明文库 → {dest / 'wechat4_plain'}")

    cfg = Path(args.config)
    if cfg.exists():
        shutil.copy2(cfg, dest / "config.yaml")
        print("✓ 配置（含密钥，注意保管） →", dest / "config.yaml")

    print(f"备份完成：{dest}（RPO ≤ 24h；每月用此目录做一次真实恢复演练）")


if __name__ == "__main__":
    main()
