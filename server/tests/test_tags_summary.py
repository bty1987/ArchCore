"""近期功能扩展回归：消息标注（F3-4）与 AI 摘要（F4-6，可插拔 LLM）。"""

from tests.conftest import ingest, msg


def _seed(client, admin_headers):
    # ts 必须相对 now:摘要窗口是「近 N 天」,硬编码日期会在翻月后炸弹(2026-10 实锤)
    from datetime import datetime, timedelta
    t_recent = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    c = client.post("/api/v1/customers", headers=admin_headers,
                    json={"name": "标签客户", "owner_user_id": 1}).json()
    ingest(client, [
        msg(svr_id="t1", sender="wxid_outside", content="明天可以报价吗", ts=t_recent),
        msg(svr_id="t2", sender="wxid_collector", content="可以，上午发您",
            ts=(datetime.utcnow() - timedelta(days=1, minutes=-5)).strftime("%Y-%m-%d %H:%M:%S")),
    ])
    sessions = client.get("/api/v1/sessions", params={"claimed": False},
                          headers=admin_headers).json()
    client.post(f"/api/v1/customers/{c['id']}/claim", headers=admin_headers,
                json={"session_ids": [s["id"] for s in sessions]})
    return c


def test_message_tags_crud_and_overview(client, admin_headers):
    c = _seed(client, admin_headers)
    msgs = client.get("/api/v1/messages", params={"q": "报价"},
                      headers=admin_headers).json()["items"]
    mid = msgs[0]["id"]

    # 打标签（重复打幂等）
    r = client.post(f"/api/v1/messages/{mid}/tags", headers=admin_headers,
                    json={"tag": "报价"})
    assert r.json()["tags"] == ["报价"]
    client.post(f"/api/v1/messages/{mid}/tags", headers=admin_headers,
                json={"tag": "报价"})
    r = client.post(f"/api/v1/messages/{mid}/tags", headers=admin_headers,
                    json={"tag": "重点"})
    assert sorted(r.json()["tags"]) == ["报价", "重点"]

    # 检索结果附带 tags
    rows = client.get("/api/v1/messages", params={"q": "报价"},
                      headers=admin_headers).json()["items"]
    assert sorted(rows[0]["tags"]) == ["报价", "重点"]

    # 客户概览含标签汇总
    ov = client.get(f"/api/v1/analytics/customers/{c['id']}/overview",
                    headers=admin_headers).json()
    tags = {t["tag"]: t["count"] for t in ov["tag_summary"]}
    assert tags.get("报价") == 1 and tags.get("重点") == 1

    # 删除标签
    r = client.delete(f"/api/v1/messages/{mid}/tags/重点", headers=admin_headers)
    assert r.json()["tags"] == ["报价"]

    # 空标签拒绝
    assert client.post(f"/api/v1/messages/{mid}/tags", headers=admin_headers,
                       json={"tag": "  "}).status_code == 422


def test_ai_summary_requires_config_and_generates(client, admin_headers, monkeypatch):
    c = _seed(client, admin_headers)

    # 未配置 AI → 400 明确报错
    r = client.post(f"/api/v1/analytics/customers/{c['id']}/summary",
                    headers=admin_headers, json={"days": 7})
    assert r.status_code == 400 and "AI 未配置" in r.json()["detail"]

    # 配置 AI（OpenAI 兼容）
    client.put("/api/v1/settings", headers=admin_headers,
               json={"key": "ai", "value": {
                   "api_base": "http://llm.internal/v1",
                   "api_key": "test-key", "model": "test-model"}})

    # monkeypatch LLM 调用（不真发请求）
    from archcore_server.services import ai as ai_svc

    def fake_call(cfg, system, user, timeout=90):
        assert "报价" in user
        return "· 客户询问报价，已承诺上午发送\n· 无风险信号"
    monkeypatch.setattr(ai_svc, "_call_llm", fake_call)

    r = client.post(f"/api/v1/analytics/customers/{c['id']}/summary",
                    headers=admin_headers, json={"days": 7})
    assert r.status_code == 200
    assert "报价" in r.json()["content"]

    # GET 返回已保存摘要
    saved = client.get(f"/api/v1/analytics/customers/{c['id']}/summary",
                       headers=admin_headers).json()
    assert saved["content"] and saved["days"] == 7

    # 生成动作写审计
    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "ai_summary" for e in logs)
