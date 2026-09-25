"""近期功能增强回归：客户概览扩展字段、关键词统计、发送者筛选、单会话导出。"""


from tests.conftest import ingest, msg


def _seed(client, admin_headers):
    c = client.post("/api/v1/customers", headers=admin_headers,
                    json={"name": "增强测试客户", "owner_user_id": 1}).json()
    ingest(client, [
        msg(svr_id="e1", sender="wxid_outside", content="这是报价单相关内容",
            ts="2026-09-20 10:00:00"),
        msg(svr_id="e2", sender="wxid_outside", content="合同条款再确认下",
            ts="2026-09-20 11:00:00"),
        msg(svr_id="e3", sender="wxid_collector", content="好的收到",
            ts="2026-09-20 11:10:00"),
    ])
    sessions = client.get("/api/v1/sessions", params={"claimed": False},
                          headers=admin_headers).json()
    client.post(f"/api/v1/customers/{c['id']}/claim", headers=admin_headers,
                json={"session_ids": [s["id"] for s in sessions]})
    return c


def test_customer_overview_extra_fields(client, admin_headers):
    c = _seed(client, admin_headers)
    ov = client.get(f"/api/v1/analytics/customers/{c['id']}/overview",
                    headers=admin_headers).json()
    assert len(ov["active_hours"]) == 24
    assert ov["type_distribution"].get("text") == 3
    words = {h["word"] for h in ov["keyword_hits"]}
    assert "报价" in words and "合同" in words


def test_keyword_stats(client, admin_headers):
    _seed(client, admin_headers)
    stats = client.get("/api/v1/analytics/keywords/stats", headers=admin_headers).json()
    by_word = {s["word"]: s["count"] for s in stats}
    assert by_word.get("报价") == 1 and by_word.get("合同") == 1
    assert list(by_word.values()) == sorted(by_word.values(), reverse=True)


def test_sender_wxid_filter(client, admin_headers):
    _seed(client, admin_headers)
    rows = client.get("/api/v1/messages", params={"sender_wxid": "wxid_collector"},
                      headers=admin_headers).json()["items"]
    assert [r["content"] for r in rows] == ["好的收到"]


def test_session_export_csv(client, admin_headers, sales_headers):
    _seed(client, admin_headers)
    sessions = client.get("/api/v1/sessions", headers=admin_headers).json()
    sid = sessions[0]["id"]
    resp = client.get(f"/api/v1/sessions/{sid}/export/csv", headers=admin_headers)
    assert resp.status_code == 200 and "sender_type" in resp.text
    # sales 无权导出（manager/admin 限定）
    assert client.get(f"/api/v1/sessions/{sid}/export/csv",
                      headers=sales_headers).status_code == 403
    # 导出写审计
    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "export_csv" for e in logs)
