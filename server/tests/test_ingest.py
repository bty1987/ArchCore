"""ingest：svr_id 优先去重、指纹兜底、sender_type 判定、幂等重放。"""

from tests.conftest import ingest, msg


def test_ingest_and_replay_idempotent(client):
    batch = [msg(svr_id=f"m{i}", sender="wxid_a", content=f"消息{i}") for i in range(10)]
    r1 = ingest(client, batch)
    assert r1.status_code == 200
    assert r1.json()["inserted"] == 10

    health = client.get(
        "/api/v1/ingest/health", headers={"X-Collector-Token": "test-collector-token"}
    )
    assert health.json()["message_count"] == 10

    # 同批重放：全部 skipped，条数不增（测试策略：ingest 幂等）
    r2 = ingest(client, batch)
    assert r2.json() == {"inserted": 0, "skipped": 10}
    assert (
        client.get(
            "/api/v1/ingest/health", headers={"X-Collector-Token": "test-collector-token"}
        ).json()["message_count"]
        == 10
    )


def test_ingest_requires_token(client):
    resp = client.post("/api/v1/ingest/messages", json={"messages": []})
    assert resp.status_code == 401
    resp = client.post(
        "/api/v1/ingest/messages", json={"messages": []}, headers={"X-Collector-Token": "wrong"}
    )
    assert resp.status_code == 401


def test_dedup_fingerprint_fallback(client):
    # 无 svr_id：同会话同发送者同秒同内容 → 指纹去重
    m1 = msg(sender="wxid_a", content="收到", ts="2026-09-01T10:00:00")
    m2 = msg(sender="wxid_a", content="收到", ts="2026-09-01T10:00:00")
    r = ingest(client, [m1, m2])
    assert r.json()["inserted"] == 1
    assert r.json()["skipped"] == 1

    # 同秒不同内容/不同发送者不误杀
    m3 = msg(sender="wxid_b", content="收到", ts="2026-09-01T10:00:00")
    m4 = msg(sender="wxid_a", content="收到，稍后回复", ts="2026-09-01T10:00:00")
    r = ingest(client, [m3, m4])
    assert r.json()["inserted"] == 2


def test_sender_type_detection(client, admin_headers):
    # 内部成员名单：wxid_staff_001 标记为同事（internal）
    client.post(
        "/api/v1/members",
        headers=admin_headers,
        json={"match_type": "wxid", "match_value": "wxid_staff_001", "display_name": "同事甲"},
    )
    batch = [
        msg(svr_id="s1", sender="wxid_collector", content="我发的"),
        msg(svr_id="s2", sender="wxid_staff_001", content="同事发的"),
        msg(svr_id="s3", sender="wxid_outside", content="客户发的"),
        msg(svr_id="s4", sender=None, content="系统消息", msg_type="system"),
    ]
    ingest(client, batch)
    rows = client.get("/api/v1/messages", headers=admin_headers).json()["items"]
    by_content = {r["content"]: r["sender_type"] for r in rows}
    assert by_content["我发的"] == "me"
    assert by_content["同事发的"] == "internal"
    assert by_content["客户发的"] == "external"
    assert by_content["系统消息"] == "system"


def test_sync_task_and_health(client):
    client.post(
        "/api/v1/ingest/sync-tasks",
        json={"type": "full_import", "status": "success", "stats": {"messages": 5}},
        headers={"X-Collector-Token": "test-collector-token", "X-Collector-Wxid": "wxid_collector"},
    )
    health = client.get(
        "/api/v1/ingest/health", headers={"X-Collector-Token": "test-collector-token"}
    )
    assert health.json()["last_sync"]["type"] == "full_import"
