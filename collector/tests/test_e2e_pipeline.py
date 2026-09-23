"""端到端：fixture 库 → 采集端（过滤/标准化/outbox）→ 进程内 server → 检索。

链路测试（工程规划 §6 第 3 行）：full_import 断言落库条数；重跑幂等；增量只补新消息。
"""

import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (
    str(REPO / "collector" / "src"),
    str(REPO / "server" / "src"),
    str(REPO / "collector"),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from archcore_server.core.config import Settings
from archcore_server.main import create_app

from archcore_collector.config import CollectorSettings, SourceConfig, WhitelistConfig
from archcore_collector.decrypt_worker.full_import import run_full_import
from archcore_collector.decrypt_worker.incr_sync import run_incr_sync
from archcore_collector.fixtures import generate
from archcore_collector.sender import Sender
from archcore_collector.state import StateStore


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("fx") / "fixture_wechat.db"
    manifest = generate(path, days=30, seed=7)
    return path, manifest


@pytest.fixture(scope="module")
def e2e(tmp_path_factory, fixture_db):
    fixture_path, manifest = fixture_db
    server_settings = Settings(
        db_url=f"sqlite:///{(tmp_path_factory.mktemp('srv') / 'srv.db').as_posix()}",
        jwt_secret="e2e-secret-key-for-tests-0123456789",
        collector_token="e2e-token",
        collector_wxid="wxid_staff_001",
        jobs_enabled=False,
    )
    app = create_app(server_settings)

    # 真实 uvicorn 线程（httpx ASGITransport 新版仅支持异步，同步 Sender 用不了）
    import socket
    import threading
    import time

    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{base_url}/api/v1/health", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("e2e server 未就绪")

    collector_settings = CollectorSettings(
        server_base_url=base_url,
        server_ingest_token="e2e-token",
        collector_wxid="wxid_staff_001",
        state_db=str(tmp_path_factory.mktemp("st") / "state.db"),
        source=SourceConfig(type="fixture", fixture_path=str(fixture_path)),
        whitelist=WhitelistConfig(groups=["11111111@chatroom", "22222222@chatroom"], allow_dm=True),
    )
    http = httpx.Client(base_url=base_url, timeout=30)
    state = StateStore(collector_settings.state_db)
    sender = Sender(http, collector_settings, state)
    yield {
        "http": http,
        "base_url": base_url,
        "state": state,
        "sender": sender,
        "settings": collector_settings,
        "manifest": manifest,
        "token_header": {"X-Collector-Token": "e2e-token"},
    }
    state.close()
    http.close()
    server.should_exit = True
    thread.join(timeout=10)


def _msg_count(e2e):
    return (
        e2e["http"]
        .get("/api/v1/ingest/health", headers=e2e["token_header"])
        .json()["message_count"]
    )


def test_full_import_and_dedup(e2e):
    manifest = e2e["manifest"]
    stats = run_full_import(e2e["settings"], e2e["sender"], e2e["state"])

    # 白名单：3 个业务会话入库，家庭群被过滤
    assert stats["sessions"] == 4  # 2 群 + 2 单聊
    assert stats["filtered"] == 1
    expected = (
        manifest["sessions"]["11111111@chatroom"]
        + manifest["sessions"]["22222222@chatroom"]
        + manifest["sessions"]["wxid_client_a"]
        + manifest["sessions"]["wxid_client_b"]
    )
    assert stats["messages"] == expected
    assert _msg_count(e2e) == expected

    # 重跑全量：svr_id 幂等去重，条数不增
    stats2 = run_full_import(e2e["settings"], e2e["sender"], e2e["state"])
    assert stats2["messages"] == expected  # flushed 口径含 skipped，落库数不变
    assert _msg_count(e2e) == expected


def test_incr_sync_watermark(e2e, fixture_db):
    fixture_path, manifest = fixture_db
    # 无新数据 → 增量为 0
    stats = run_incr_sync(e2e["settings"], e2e["sender"], e2e["state"])
    assert stats["messages"] == 0

    # 向 fixture 库追加 3 条新消息（其中 1 条发到被过滤的家庭群）
    import sqlite3

    conn = sqlite3.connect(str(fixture_path))
    base = conn.execute("SELECT MAX(ts) FROM msg").fetchone()[0]
    for svr_id, wx_id, sender, content in [
        ("new1", "11111111@chatroom", "wxid_client_a", "增量消息一"),
        ("new2", "wxid_client_a", "wxid_client_a", "增量消息二"),
        ("new3", "33333333@chatroom", "wxid_family_1", "不该被采集"),
    ]:
        # ts 取全局最大 +1 分钟，确保落在各会话水位之后
        conn.execute(
            "INSERT INTO msg VALUES(?,?,?,'text',?,datetime(?, '+1 minute'),0,NULL)",
            (svr_id, wx_id, sender, content, base),
        )
    conn.commit()
    conn.close()

    stats = run_incr_sync(e2e["settings"], e2e["sender"], e2e["state"])
    assert stats["messages"] == 2  # 家庭群消息被白名单拦截
    assert _msg_count(e2e) == (
        manifest["sessions"]["11111111@chatroom"]
        + manifest["sessions"]["22222222@chatroom"]
        + manifest["sessions"]["wxid_client_a"]
        + manifest["sessions"]["wxid_client_b"]
        + 2
    )


def test_outbox_retry_on_failure(e2e, monkeypatch):
    """server 不可达时批次留在 outbox 退避重试，恢复后冲刷成功。"""
    state, _settings = e2e["state"], e2e["settings"]
    batch = {
        "schema_ver": 1,
        "messages": [
            {
                "session": {"wx_id": "g_retry@chatroom", "type": "group", "name": "重试群"},
                "svr_id": "retry1",
                "sender_wxid": "wxid_a",
                "msg_type": "text",
                "content": "重试消息",
                "ts": "2026-09-20 10:00:00",
                "source": "decrypt",
            }
        ],
    }
    import json

    state.enqueue(json.dumps(batch))
    row = state.take_pending(1)
    assert row  # 待发批次在队列

    # 用一个指向不可达地址的 settings 模拟故障（Sender 目标取自 settings.server_base_url）
    import httpx as _hx

    bad_settings = e2e["settings"].model_copy(deep=True)
    bad_settings.server_base_url = "http://127.0.0.1:1"
    bad_client = _hx.Client(base_url="http://127.0.0.1:1", timeout=2)
    bad_sender = Sender(bad_client, bad_settings, state)
    assert bad_sender.flush() == 0
    assert state.pending_count() == 1  # 失败退避留在队列

    # 恢复：等退避窗口（2s）过后，真实 server 冲刷成功
    time.sleep(2.2)
    assert e2e["sender"].flush() == 1
    assert state.pending_count() == 0
    assert _msg_count(e2e) >= 1
    bad_client.close()


def test_server_search_after_ingest(e2e):
    admin = (
        e2e["http"]
        .post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"})
        .json()
    )
    headers = {"Authorization": f"Bearer {admin['token']}"}
    rows = e2e["http"].get("/api/v1/messages", params={"q": "增量消息一"}, headers=headers).json()
    assert len(rows["items"]) == 1
    # 家庭群数据不可检索（白名单外根本未入库）
    rows = e2e["http"].get("/api/v1/messages", params={"q": "不该被采集"}, headers=headers).json()
    assert len(rows["items"]) == 0
