"""性能验证（PRD 验收 #3）：灌 10 万条消息，组合检索 <2s。

用法：python scripts/perf_check.py [--rows 100000]
直接用 SQLAlchemy 批量灌库（绕过 API 层，只测存储与检索层）。
"""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))

REPO = Path(__file__).resolve().parents[1]


def main(rows: int = 100_000) -> None:
    import tempfile

    from archcore_server.core.config import Settings
    from archcore_server.models import Base, ChatSession, Message
    from archcore_server.services.analysis import search_messages
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    tmp = tempfile.mkdtemp(prefix="archcore-perf-")
    db_path = Path(tmp) / "perf.db"
    settings = Settings(db_url=f"sqlite:///{db_path.as_posix()}", jobs_enabled=False)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        from archcore_server.core.db import FTS_SQL
        from sqlalchemy import text

        for stmt in FTS_SQL:
            conn.execute(text(stmt))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    print(f"[1/3] 灌入 {rows} 条消息到 {db_path}")
    t0 = time.perf_counter()
    with factory() as db:
        sess = ChatSession(wx_id="perf@chatroom", type="group", name="性能测试群", customer_id=None)
        db.add(sess)
        db.flush()
        base = datetime(2025, 1, 1)
        CHUNK = 5000
        for offset in range(0, rows, CHUNK):
            n = min(CHUNK, rows - offset)
            db.execute(
                Message.__table__.insert(),
                [
                    {
                        "session_id": sess.id,
                        "svr_id": f"perf{i}",
                        "fingerprint": None,
                        "sender_wxid": f"wxid_{i % 50}",
                        "sender_type": "external" if i % 3 else "internal",
                        "msg_type": "text",
                        "content": f"性能测试消息 {i} 报价单进展跟踪 {i % 97}",
                        "media_path": None,
                        "media_meta": None,
                        "ts": base + timedelta(minutes=i),
                        "recalled": False,
                        "source": "decrypt",
                        "raw": None,
                        "created_at": datetime.utcnow(),
                    }
                    for i in range(offset, offset + n)
                ],
            )
        db.commit()  # Session 上下文退出只 close，需显式提交
    print(f"      灌入耗时 {time.perf_counter() - t0:.1f}s")

    with factory() as db:
        total = db.scalar(select(Message.id).limit(1))
        assert total is not None
        print("[2/3] FTS 中文检索（q=报价单进展）")
        t0 = time.perf_counter()
        items, _ = search_messages(db, q="报价单进展", limit=50)
        dt_fts = time.perf_counter() - t0
        print(f"      命中 {len(items)} 条，耗时 {dt_fts * 1000:.0f}ms")

        print("[3/3] 组合过滤（时间窗 + sender_type + msg_type + session）")
        t0 = time.perf_counter()
        items, _ = search_messages(
            db,
            session_id=1,
            from_ts=datetime(2025, 3, 1),
            to_ts=datetime(2025, 12, 31),
            sender_type="external",
            msg_type="text",
            limit=50,
        )
        dt_combo = time.perf_counter() - t0
        print(f"      命中 {len(items)} 条，耗时 {dt_combo * 1000:.0f}ms")

    ok = dt_fts < 2.0 and dt_combo < 2.0
    print(
        f"\n结果：FTS {dt_fts:.3f}s / 组合 {dt_combo:.3f}s —— "
        f"{'✅ 满足 <2s 验收' if ok else '❌ 不达标：先加索引/调 FTS 分词，不换数据库（测试策略）'}"
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    args = parser.parse_args()
    main(args.rows)
