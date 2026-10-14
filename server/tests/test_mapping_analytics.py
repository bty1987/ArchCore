"""映射、聚合分析、健康度、导出与审计。"""

from datetime import datetime, timedelta

from sqlalchemy import text

from tests.conftest import app_state, ingest, msg


def _seed_and_claim(client, admin_headers):
    c = client.post(
        "/api/v1/customers", headers=admin_headers, json={"name": "分析客户", "owner_user_id": 1}
    ).json()
    # 固定到 10 点档:UTC 午夜前 1 小时运行时 +1h 会跨日(2026-10-15 实锤的时间炸弹)
    base = (datetime.utcnow() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    ingest(
        client,
        [
            msg(
                svr_id="a1",
                sender="wxid_outside",
                content="需求确认",
                ts=(base).isoformat(sep=" ", timespec="seconds"),
            ),
            msg(
                svr_id="a2",
                sender="wxid_collector",
                content="好的",
                ts=(base + timedelta(minutes=30)).isoformat(sep=" ", timespec="seconds"),
            ),
            msg(
                svr_id="a3",
                sender="wxid_outside",
                content="收到",
                ts=(base + timedelta(hours=1)).isoformat(sep=" ", timespec="seconds"),
            ),
        ],
    )
    sessions = client.get(
        "/api/v1/sessions", params={"claimed": False}, headers=admin_headers
    ).json()
    client.post(
        f"/api/v1/customers/{c['id']}/claim",
        headers=admin_headers,
        json={"session_ids": [s["id"] for s in sessions]},
    )
    return c


def test_unclaimed_and_map(client, admin_headers):
    ingest(
        client,
        [
            msg(svr_id="m1"),
            msg(svr_id="m2", session={"wx_id": "g2@chatroom", "type": "group", "name": "二号群"}),
        ],
    )
    unclaimed = client.get("/api/v1/sessions/unclaimed", headers=admin_headers).json()
    assert len(unclaimed) == 2
    c = client.post("/api/v1/customers", headers=admin_headers, json={"name": "映射客户"}).json()
    client.post(
        f"/api/v1/sessions/{unclaimed[0]['id']}/map",
        headers=admin_headers,
        json={"customer_id": c["id"]},
    )
    unclaimed2 = client.get("/api/v1/sessions/unclaimed", headers=admin_headers).json()
    assert len(unclaimed2) == 1
    # 解除映射 → 回到待认领
    client.post(
        f"/api/v1/sessions/{unclaimed[0]['id']}/map",
        headers=admin_headers,
        json={"customer_id": None},
    )
    assert len(client.get("/api/v1/sessions/unclaimed", headers=admin_headers).json()) == 2


def test_aggregate_and_dashboard(client, admin_headers):
    _seed_and_claim(client, admin_headers)
    from archcore_server.services.analysis import recompute_daily

    db = app_state(client).session_factory()
    try:
        assert recompute_daily(db, days=3) >= 1
    finally:
        db.close()
    dash = client.get("/api/v1/dashboard", headers=admin_headers).json()
    assert dash["total_customers"] == 1
    assert dash["claimed_sessions"] >= 1
    assert dash["today_messages"] >= 0
    trends = client.get("/api/v1/analytics/trends", headers=admin_headers).json()
    assert any(t["total"] == 3 for t in trends)


def test_customer_overview_response_latency(client, admin_headers):
    c = _seed_and_claim(client, admin_headers)
    from archcore_server.jobs.aggregate import run  # noqa: F401  聚合先跑一次
    from archcore_server.services.analysis import recompute_daily

    db = app_state(client).session_factory()
    try:
        recompute_daily(db, days=3)
    finally:
        db.close()
    overview = client.get(
        f"/api/v1/analytics/customers/{c['id']}/overview", headers=admin_headers
    ).json()
    assert overview["session_count"] >= 1
    # 10:00 客户问 → 10:30 我方回（30 分钟）；11:00 客户问未回（未达标样本）
    assert overview["response"]["samples"] == 2
    assert overview["response"]["p50_minutes"] == 30
    assert overview["response"]["sla_rate"] == 0.5


def test_health_recompute(client, admin_headers):
    _seed_and_claim(client, admin_headers)
    from archcore_server.jobs.health import recompute_health

    db = app_state(client).session_factory()
    try:
        assert recompute_health(db) == 1
        row = db.execute(text("SELECT health_score, health_level FROM customer")).fetchone()
        assert row[0] is not None and row[1] in ("red", "yellow", "green")
    finally:
        db.close()


def test_export_csv_writes_audit(client, admin_headers):
    _seed_and_claim(client, admin_headers)
    client.get("/api/v1/sessions", headers=admin_headers).json()
    resp = client.get("/api/v1/customers/1/export/csv", headers=admin_headers)
    assert resp.status_code == 200
    assert "sender_type" in resp.text and "需求确认" in resp.text
    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "export_csv" for e in logs)


def test_fingerprint_stability():
    """同输入永远同指纹（单测锁定，防实现漂移）。"""
    from archcore_server.services.ingest import compute_fingerprint

    ts = datetime(2026, 9, 1, 10, 0, 0)
    a = compute_fingerprint("g1@chatroom", "wxid_a", ts, "内容")
    b = compute_fingerprint("g1@chatroom", "wxid_a", ts, "内容")
    c = compute_fingerprint("g1@chatroom", "wxid_a", ts, "不同内容")
    assert a == b and a != c


def test_keyword_admin(client, admin_headers):
    r = client.post(
        "/api/v1/keywords", headers=admin_headers, json={"category": "risk", "word": "解约"}
    )
    assert r.status_code == 200
    items = client.get(
        "/api/v1/keywords", params={"category": "risk"}, headers=admin_headers
    ).json()
    assert any(k["word"] == "解约" for k in items)
    # 命中新词触发预警
    ingest(
        client,
        [
            msg(
                svr_id="kw1",
                sender="wxid_outside",
                content="我们考虑解约。",
                ts=datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
            )
        ],
    )
    alerts = client.get("/api/v1/alerts", headers=admin_headers).json()
    assert any(
        a["rule_code"] == "risk_keyword" and a["detail"].get("keyword") == "解约" for a in alerts
    )
