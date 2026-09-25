"""会话白名单服务端管控：页面 CRUD、采集端拉取、会话清单上报。"""


def test_whitelist_crud_and_collector_fetch(client, admin_headers):
    # 初始：未配置（无规则、未开 allow_all）→ 采集端视角 groups 为空
    body = client.get(
        "/api/v1/ingest/whitelist", headers={"X-Collector-Token": "test-collector-token"}
    ).json()
    assert body == {"allow_all": False, "groups": []}

    # 新增规则（upsert 语义）
    r = client.post(
        "/api/v1/whitelist",
        headers=admin_headers,
        json={"wx_id": "123@chatroom", "stype": "group", "name": "客户群"},
    )
    assert r.status_code == 200
    client.post(
        "/api/v1/whitelist",
        headers=admin_headers,
        json={"wx_id": "123@chatroom", "stype": "group", "name": "客户群改名"},
    )
    rules = client.get("/api/v1/whitelist", headers=admin_headers).json()["rules"]
    assert len(rules) == 1 and rules[0]["name"] == "客户群改名"

    # 采集端拉取：命中规则
    body = client.get(
        "/api/v1/ingest/whitelist", headers={"X-Collector-Token": "test-collector-token"}
    ).json()
    assert body["groups"] == ["123@chatroom"] and body["allow_all"] is False

    # allow_all 开关
    client.put("/api/v1/whitelist/allow-all", headers=admin_headers, json={"enabled": True})
    body = client.get(
        "/api/v1/ingest/whitelist", headers={"X-Collector-Token": "test-collector-token"}
    ).json()
    assert body["allow_all"] is True

    # 删除规则后 groups 空、allow_all 仍在
    client.delete(f"/api/v1/whitelist/{rules[0]['id']}", headers=admin_headers)
    body = client.get(
        "/api/v1/ingest/whitelist", headers={"X-Collector-Token": "test-collector-token"}
    ).json()
    assert body["groups"] == [] and body["allow_all"] is True

    # 审计留痕
    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "whitelist_add" for e in logs)


def test_whitelist_requires_manager(client, sales_headers):
    assert client.get("/api/v1/whitelist", headers=sales_headers).status_code == 403
    assert (
        client.post("/api/v1/whitelist", headers=sales_headers, json={"wx_id": "x"}).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/whitelist/allow-all", headers=sales_headers, json={"enabled": True}
        ).status_code
        == 403
    )


def test_ingest_sessions_inventory(client):
    """采集端上报会话清单 → chat_session 建立（白名单页与待认领的数据源）。"""
    coll = {"X-Collector-Token": "test-collector-token"}
    r = client.post(
        "/api/v1/ingest/sessions",
        headers=coll,
        json={
            "sessions": [
                {"wx_id": "777@chatroom", "type": "group", "name": "新发现的群"},
                {"wx_id": "wxid_x", "type": "dm", "name": "某联系人"},
            ]
        },
    )
    assert r.json() == {"known": 2, "received": 2}
    # 重复上报不重复建
    r = client.post(
        "/api/v1/ingest/sessions",
        headers=coll,
        json={
            "sessions": [
                {"wx_id": "777@chatroom", "type": "group", "name": "新发现的群"},
            ]
        },
    )
    assert r.json()["known"] == 0
    # 无 token 拒绝
    assert client.post("/api/v1/ingest/sessions", json={"sessions": []}).status_code == 401
