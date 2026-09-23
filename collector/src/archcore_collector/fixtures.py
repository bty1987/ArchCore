"""脱敏合成数据生成器（gen-fixtures）：开发、测试、演示环境专用。

红线：任何真实会话数据不入仓库、不进演示环境。
生成 SQLite 样本库（sources.FixtureSource 可读），内容确定性可复现（seed 固定）。
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
  wx_id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS msg (
  svr_id TEXT PRIMARY KEY, session_wx_id TEXT NOT NULL, sender_wxid TEXT,
  msg_type TEXT NOT NULL DEFAULT 'text', content TEXT DEFAULT '',
  ts TEXT NOT NULL, recalled INTEGER NOT NULL DEFAULT 0, media_meta TEXT
);
CREATE INDEX IF NOT EXISTS ix_msg_session_ts ON msg(session_wx_id, ts);
CREATE TABLE IF NOT EXISTS contact (
  wx_id TEXT PRIMARY KEY, nickname TEXT DEFAULT '', remark TEXT DEFAULT ''
);
"""

SESSIONS = [
    ("11111111@chatroom", "group", "ABC项目群"),
    ("22222222@chatroom", "group", "DEF项目群"),
    ("33333333@chatroom", "group", "家庭群"),  # 非业务群：白名单测试用
    ("wxid_client_a", "dm", "客户A-张总"),
    ("wxid_client_b", "dm", "客户B-李经理"),
]

INTERNAL_MEMBERS = ["wxid_staff_001", "wxid_staff_002"]
EXTERNAL_MEMBERS = {
    "11111111@chatroom": ["wxid_client_a", "wxid_client_c"],
    "22222222@chatroom": ["wxid_client_b"],
    "33333333@chatroom": ["wxid_family_1", "wxid_family_2"],
}

TEXT_POOL = [
    "今天下午三点开会，请准时参加。",
    "这个版本的报价单什么时候能给到？",
    "收到，我马上安排。",
    "方案初稿已发群里，大家看一下。",
    "合同条款我们法务还在看，明天回复。",
    "这个问题我们要投诉，太影响交付了。",
    "服务器宕机了，客户在群里催了。",
    "下周一一起过一下验收标准。",
    "发票已寄出，注意查收。",
    "竞品上周发布了新版本，价格低 20%。",
]

RISK_LINES = [
    "再拖下去我们只能退款了。",
    "给你们最后一次机会，不然就找竞品了。",
    "我要投诉你们的服务态度。",
]


def generate(db_path: str | Path, days: int = 120, seed: int = 42) -> dict:
    """生成样本库，返回 manifest（各会话消息数等，供测试断言与演示统计）。"""
    rng = random.Random(seed)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(db_path).exists():
        Path(db_path).unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    conn.executemany("INSERT INTO session VALUES(?,?,?)", SESSIONS)
    conn.executemany(
        "INSERT INTO contact VALUES(?,?,?)",
        [("wxid_client_a", "张总", "客户A-张总"), ("wxid_client_b", "李经理", "客户B-李经理")],
    )

    now = datetime.now().replace(microsecond=0)
    start = now - timedelta(days=days)
    svr_seq = 0
    counts: dict[str, int] = {}
    risk_count = 0

    for wx_id, _type, name in SESSIONS:
        if wx_id == "33333333@chatroom":
            msgs_per_day = 3
        elif wx_id.endswith("@chatroom"):
            msgs_per_day = 8
        else:
            msgs_per_day = 2
        members = EXTERNAL_MEMBERS.get(wx_id, [])
        all_senders = members + INTERNAL_MEMBERS
        cur = start
        while cur < now:
            for _ in range(msgs_per_day):
                ts = cur + timedelta(minutes=rng.randint(8 * 60, 20 * 60))
                if ts >= now:
                    break
                svr_seq += 1
                roll = rng.random()
                if roll < 0.04:
                    sender, mtype, content = None, "system", f'"{name}" 邀请新成员进群'
                elif roll < 0.10:
                    sender, mtype = rng.choice(members or all_senders), "image"
                    content = ""
                elif roll < 0.13:
                    sender, mtype = rng.choice(all_senders), "file"
                    content = ""
                elif roll < 0.145:
                    sender, mtype = rng.choice(all_senders), "quote"
                    content = "引用了之前的消息"
                else:
                    sender, mtype = rng.choice(all_senders), "text"
                    content = (
                        rng.choice(RISK_LINES) if rng.random() < 0.03 else rng.choice(TEXT_POOL)
                    )
                if mtype == "text" and content in RISK_LINES:
                    risk_count += 1
                media_meta = None
                if mtype == "image":
                    media_meta = json.dumps({"width": 800, "height": 600})
                elif mtype == "file":
                    media_meta = json.dumps(
                        {"filename": rng.choice(["合同V3.pdf", "报价单.xlsx", "需求说明.docx"])}
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO msg VALUES(?,?,?,?,?,?,?,?)",
                    (
                        f"fx{svr_seq:08d}",
                        wx_id,
                        sender,
                        mtype,
                        content,
                        ts.isoformat(sep=" "),
                        1 if rng.random() < 0.01 else 0,
                        media_meta,
                    ),
                )
                counts[wx_id] = counts.get(wx_id, 0) + 1
            cur += timedelta(days=1)
    conn.commit()
    conn.close()
    return {
        "db_path": str(db_path),
        "sessions": {wx_id: counts.get(wx_id, 0) for wx_id, _, _ in SESSIONS},
        "total_messages": sum(counts.values()),
        "risk_hits": risk_count,
        "svr_id_range": svr_seq,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成脱敏合成微信样本库")
    parser.add_argument("--out", default="./data/fixture_wechat.db")
    parser.add_argument("--days", type=int, default=120)
    args = parser.parse_args()
    print(json.dumps(generate(args.out, args.days), ensure_ascii=False, indent=2))
