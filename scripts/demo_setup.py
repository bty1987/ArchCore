"""demo_setup.py — 演示模式配套设置(差距分析 P0 #7)。

两个子命令,由 run-demo.bat 在不同阶段调用:

  python scripts/demo_setup.py init
      生成 data/demo/collector_config.yaml(fixture 源/allow_all/演示 token),
      在服务启动前调用。

  python scripts/demo_setup.py seed
      直连 ARCHCORE_DB_URL 指向的演示库,做三件事:
      1. 建演示客户并认领会话(库迪式合成客户);
      2. upsert 演示预警规则;
      3. 场景整形:把「家庭群」最近 10 天消息整体前移(制造客户沉默场景)、
         「DEF项目群」最近 35 天消息前移(制造群不活跃场景);
      然后跑聚合与三类巡检,演示打开即有预警。与真实数据完全隔离。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "src"))

DEMO_TOKEN = "demo-collector-token"
DEMO_WXID = "wxid_demo_collector"


def init() -> None:
    import yaml

    out = ROOT / "data" / "demo" / "collector_config.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = {
        "server_base_url": "http://127.0.0.1:8000",
        "server_ingest_token": DEMO_TOKEN,
        "collector_wxid": DEMO_WXID,
        "state_db": str(ROOT / "data" / "demo" / "collector_state.db"),
        "source": {
            "type": "fixture",
            "fixture_path": str(ROOT / "data" / "demo" / "fixture_wechat.db"),
        },
        "whitelist": {"allow_all": True},
    }
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    print(f"[demo] collector demo config -> {out}")


def seed() -> None:
    from sqlalchemy import create_engine, select, update
    from sqlalchemy.orm import sessionmaker

    from archcore_server.models import (
        AlertRule,
        ChatSession,
        Customer,
        Message,
    )
    from archcore_server.jobs import aggregate
    from archcore_server.services import alert_engine

    db_url = os.environ.get("ARCHCORE_DB_URL")
    if not db_url:
        sys.exit("[demo] ARCHCORE_DB_URL 未设置——请经 run-demo.bat 调用")
    engine = create_engine(db_url)
    factory = sessionmaker(bind=engine)
    now = datetime.utcnow()

    with factory() as db:
        # 0. admin 密码设为演示密码(不同于 bootstrap):登录不再触发强制改密
        from archcore_server.core.security import hash_password, verify_password
        from archcore_server.models import AppUser

        DEMO_PASSWORD = "demo-arch-2026"
        admin = db.scalar(select(AppUser).where(AppUser.username == "admin"))
        if admin is not None and not verify_password(DEMO_PASSWORD, admin.password_hash):
            admin.password_hash = hash_password(DEMO_PASSWORD)

        # 1. 演示客户 + 认领(业务群/单聊 → 客户;家庭群保持待认领演示映射工作流)
        demo_map = [
            ("ABC项目群", "库迪咖啡供应链群", "contact"),
            ("客户A-张总", "客户A-张总", "quote"),
            ("客户B-李经理", "客户B-李经理", "contact"),
        ]
        for wx_name, cust_name, stage in demo_map:
            sess = db.scalar(select(ChatSession).where(ChatSession.name == wx_name))
            if sess is None:
                print(f"[demo] 会话不存在,跳过: {wx_name}")
                continue
            cust = db.scalar(select(Customer).where(Customer.name == cust_name))
            if cust is None:
                cust = Customer(name=cust_name, industry="演示", stage=stage, owner_user_id=1)
                db.add(cust)
                db.flush()
            sess.customer_id = cust.id

        # 2. 演示预警规则 upsert
        for rule in alert_engine.DEFAULT_RULES:
            row = db.scalar(select(AlertRule).where(AlertRule.code == rule["code"]))
            if row is None:
                db.add(AlertRule(code=rule["code"], level=rule["level"],
                                 cooldown_minutes=rule["cooldown_minutes"],
                                 params=rule.get("params", {})))
            else:
                row.enabled = True

        # 3. 场景整形(只动演示库):
        #    客户B(已认领单聊)最近 10 天消息前移 15 天 → customer_silence(7 天)触发;
        #    DEF群最近 50 天消息前移 55 天 → session_inactive(30 天)触发
        cust_b = db.scalar(select(ChatSession).where(ChatSession.name == "客户B-李经理"))
        if cust_b is not None:
            db.execute(
                update(Message)
                .where(Message.session_id == cust_b.id, Message.ts >= now - timedelta(days=10))
                .values(ts=Message.ts - timedelta(days=15))
            )
        defg = db.scalar(select(ChatSession).where(ChatSession.name == "DEF项目群"))
        if defg is not None:
            db.execute(
                update(Message)
                .where(Message.session_id == defg.id, Message.ts >= now - timedelta(days=50))
                .values(ts=Message.ts - timedelta(days=55))
            )
        # 同步 last_msg_at 冗余列(session_inactive 按它判定)
        from sqlalchemy import func

        for sess in filter(None, (cust_b, defg)):
            new_max = db.execute(
                select(func.max(Message.ts)).where(Message.session_id == sess.id)
            ).scalar()
            sess.last_msg_at = new_max
        db.commit()

        # 3.5 今日铺量:走标准 /ingest 通道给「今天」注入合成消息(工作台今日消息量不再空)
        #     只铺 ABC 群与客户A——客户B 保持沉默预警、DEF 群保持不活跃预警,场景不破坏;
        #     svr_id 按日幂等,同日重复 seed 不重复入库
        _seed_today_messages()

        # 4. 聚合 + 巡检立即跑一轮(演示打开即有数据/预警)
        aggregate.run(factory)
        n_stale = alert_engine.collect_stale_inspection(db, now)
        n_sil, n_inact = alert_engine.silence_inspection(db, now), alert_engine.inactive_inspection(db, now)
        db.commit()
        print(f"[demo] 巡检完成: collect_stale={n_stale} silence={n_sil} inactive={n_inact}")
        print("[demo] 登录: admin / demo-arch-2026(seed 直设,不触发强制改密)")


def _seed_today_messages() -> None:
    """给今天注入业务感合成消息(demo 专用;server 须已启动,失败只警告不中断)。"""
    import random

    import httpx

    rng = random.Random(20261015)
    now = datetime.now()
    start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if start >= now:
        start = now.replace(hour=0, minute=30, second=0, microsecond=0)
    span = max((now - start).total_seconds() - 300, 600)  # 铺到 now-5min,至少 10 分钟窗

    plans = [
        # (会话 wx_id/type/name, 发送者池, 条数, 内容池)
        (("11111111@chatroom", "group", "ABC项目群"),
         ["wxid_client_a", "wxid_staff_001", "wxid_staff_002", "wxid_client_b"], 14,
         ["第二批设备的排期出来了吗", "本周五前交付 A 仓,下周二 B 仓", "报价单我更新了,含税价按上次约定",
          "发票抬头发我一下,今天开出来", "物流单号稍后同步到群里", "验收标准按合同附件三执行",
          "这批要加急,运费我们承担", "收到,我这边今天安排质检", "合同扫描件已归档,需要的话我发你",
          "下周一例会改成线上,链接稍后发", "备件库存还剩 40 套,建议补货", "客户问能不能提前两天",
          "工地那边今天反馈进度正常", "好的,按这个节奏推进"]),
        (("wxid_client_a", "dm", "客户A-张总"),
         ["wxid_client_a", "wxid_staff_001"], 4,
         ["张总,上周说的方案我整理好了", "下午三点方便通个电话吗", "方案里报价部分我们再对一下",
          "好,那按电话里说的,周五前给我修订版"]),
    ]
    day = now.strftime("%Y%m%d")
    messages = []
    seq = 0
    for session, senders, count, contents in plans:
        for i in range(count):
            seq += 1
            ts = start + timedelta(seconds=span * (i + rng.uniform(0, 0.8)) / count)
            if ts >= now:
                ts = now - timedelta(minutes=5)
            messages.append({
                "session": {"wx_id": session[0], "type": session[1], "name": session[2]},
                "svr_id": f"demo_today_{day}_{seq}",
                "sender_wxid": rng.choice(senders),
                "msg_type": "text",
                "content": contents[i % len(contents)],
                "ts": ts.isoformat(sep=" ", timespec="seconds"),
                "source": "demo",
            })
    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/api/v1/ingest/messages",
            json={"schema_ver": 1, "messages": messages},
            headers={"X-Collector-Token": DEMO_TOKEN},
            timeout=30,
        )
        stat = resp.json().get("stats", resp.json())
        print(f"[demo] 今日铺量: {stat}")
    except Exception as exc:  # server 未起或端口占用:不阻断 seed 其余步骤
        print(f"[demo] 今日铺量跳过(server 未就绪): {exc}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "init":
        init()
    elif cmd == "seed":
        seed()
    else:
        sys.exit("用法: python scripts/demo_setup.py init|seed")
