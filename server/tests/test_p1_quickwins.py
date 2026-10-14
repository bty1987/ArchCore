"""P1 快赢回归:AI 经营周报 / AI 管家 / 管道仪表。"""

from datetime import datetime, timedelta

from sqlalchemy import text

from tests.conftest import ingest, msg


def _setup_data(client, admin_headers):
    c = client.post(
        "/api/v1/customers", headers=admin_headers, json={"name": "周报客户"}
    ).json()
    base = (datetime.utcnow() - timedelta(days=1)).replace(hour=10, minute=0, second=0)
    ingest(client, [
        msg(svr_id="r1", sender="wxid_outside", content="报价什么时候发", ts=base.isoformat(sep=" ", timespec="seconds")),
        msg(svr_id="r2", sender="wxid_collector", content="今天上午发您", ts=(base + timedelta(minutes=30)).isoformat(sep=" ", timespec="seconds")),
    ])
    sessions = client.get("/api/v1/sessions", params={"claimed": False}, headers=admin_headers).json()
    client.post(f"/api/v1/customers/{c['id']}/claim", headers=admin_headers,
                json={"session_ids": [s["id"] for s in sessions]})
    return c


def _config_ai(client, admin_headers):
    client.put("/api/v1/settings", headers=admin_headers, json={
        "key": "ai", "value": {"api_base": "http://llm.internal/v1", "api_key": "k", "model": "m"}})


def _patch_llm(monkeypatch, expect_in_user=None):
    from archcore_server.services import ai as ai_svc

    def fake_call(cfg, system, user, timeout=90):
        if expect_in_user is not None:
            assert expect_in_user in user, f"LLM 上下文缺 {expect_in_user}"
        return "AI 生成内容测试"
    monkeypatch.setattr(ai_svc, "_call_llm", fake_call)


def test_report_requires_ai(client, admin_headers):
    _setup_data(client, admin_headers)
    r = client.post("/api/v1/analytics/report?days=7", headers=admin_headers)
    assert r.status_code == 400 and "AI 未配置" in r.json()["detail"]


def test_report_generate_and_get(client, admin_headers, monkeypatch):
    _setup_data(client, admin_headers)
    _config_ai(client, admin_headers)
    _patch_llm(monkeypatch, expect_in_user="total_messages")

    r = client.post("/api/v1/analytics/report?days=7", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "AI 生成内容测试" in body["content"]
    assert body["stats"]["total_messages"] == 2
    assert body["stats"]["alerts_total"] >= 0

    saved = client.get("/api/v1/analytics/report", headers=admin_headers).json()
    assert saved["content"] == body["content"]

    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "report_generate" for e in logs)


def test_pipeline_stats(client, admin_headers):
    _setup_data(client, admin_headers)
    db = client.app.state.session_factory()
    now = datetime.utcnow()
    db.execute(text(
        "INSERT INTO sync_task(type,status,stats,log,collector_wxid,created_at,finished_at) "
        "VALUES('incr_sync','success','{}','','wxid_c',:c,:f)"),
        {"c": (now - timedelta(hours=2)).isoformat(sep=" "), "f": (now - timedelta(hours=2, minutes=-5)).isoformat(sep=" ")})
    db.execute(text(
        "INSERT INTO sync_task(type,status,stats,log,collector_wxid,created_at,finished_at) "
        "VALUES('incr_sync','failed','{}','boom','wxid_c',:c,:f)"),
        {"c": (now - timedelta(hours=1)).isoformat(sep=" "), "f": (now - timedelta(hours=1)).isoformat(sep=" ")})
    db.commit()

    r = client.get("/api/v1/ingest/pipeline-stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["sync_total"] == 2
    assert body["sync_failed"] == 1
    assert body["sync_success_rate"] == 50.0
    assert body["last_failed"]["log"] == "boom"
    assert isinstance(body["messages_daily"], list)


def test_assistant_query(client, admin_headers, monkeypatch):
    _setup_data(client, admin_headers)
    _config_ai(client, admin_headers)
    _patch_llm(monkeypatch, expect_in_user="报价")

    # 未配置时 400
    # (此用例顺序在配置后,另开一个未配置 client 不便;配置检查由 report 用例覆盖)

    r = client.post("/api/v1/assistant/query", headers=admin_headers,
                    json={"question": "客户问报价了吗"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "AI 生成内容测试"
    assert isinstance(body["hits"], list)

    # 空问题 400
    assert client.post("/api/v1/assistant/query", headers=admin_headers,
                       json={"question": "  "}).status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "assistant_query" for e in logs)
