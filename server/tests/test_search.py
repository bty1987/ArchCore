"""检索：FTS trigram（≥3 字符）、LIKE 回退（2 字符）、组合过滤、上下文、keyset 分页。"""

from tests.conftest import ingest, msg

TEXTS = [
    ("t1", "wxid_a", "合同条款我们法务还在审阅", "2026-09-01T09:00:00"),
    ("t2", "wxid_b", "新的报价单已发送，请查收", "2026-09-02T10:00:00"),
    ("t3", "wxid_collector", "收到，明天给答复", "2026-09-02T10:05:00"),
    ("t4", "wxid_a", "价格能不能再优惠一些", "2026-09-03T14:00:00"),
]


def _seed(client):
    ingest(client, [msg(svr_id=s, sender=w, content=c, ts=t) for s, w, c, t in TEXTS])


def test_fts_search_three_chars(client, admin_headers):
    _seed(client)
    rows = client.get("/api/v1/messages", params={"q": "报价单"}, headers=admin_headers).json()[
        "items"
    ]
    assert len(rows) == 1 and "报价单" in rows[0]["content"]


def test_search_two_chars_like_fallback(client, admin_headers):
    _seed(client)
    rows = client.get("/api/v1/messages", params={"q": "优惠"}, headers=admin_headers).json()[
        "items"
    ]
    assert len(rows) == 1


def test_search_combo_filters(client, admin_headers):
    _seed(client)
    rows = client.get(
        "/api/v1/messages",
        params={"sender_type": "external", "from_ts": "2026-09-02T00:00:00"},
        headers=admin_headers,
    ).json()["items"]
    assert [r["svr_id"] for r in rows] == ["t2", "t4"]


def test_pagination_keyset(client, admin_headers):
    _seed(client)
    p1 = client.get("/api/v1/messages", params={"limit": 2}, headers=admin_headers).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = client.get(
        "/api/v1/messages", params={"limit": 2, "cursor": p1["next_cursor"]}, headers=admin_headers
    ).json()
    assert p2["items"][0]["id"] > p1["items"][-1]["id"]


def test_context_endpoint(client, admin_headers):
    _seed(client)
    items = client.get("/api/v1/messages", params={"q": "报价单"}, headers=admin_headers).json()[
        "items"
    ]
    ctx = client.get(f"/api/v1/messages/{items[0]['id']}/context", headers=admin_headers).json()
    contents = [c["content"] for c in ctx]
    assert "合同条款我们法务还在审阅" in contents  # 前文包含
    assert ctx[-1]["content"] == "价格能不能再优惠一些"


def test_sales_scoped_messages(client, admin_headers, sales_headers):
    # 建客户（owner=sales1 uid=2）并映射 g1 群，再验证 sales 只见该客户消息
    c = client.post(
        "/api/v1/customers", headers=admin_headers, json={"name": "客户甲", "owner_user_id": 2}
    ).json()
    _seed(client)
    sess = client.get("/api/v1/sessions", params={"claimed": False}, headers=admin_headers).json()
    client.post(
        f"/api/v1/sessions/{sess[0]['id']}/map",
        headers=admin_headers,
        json={"customer_id": c["id"]},
    )
    mine = client.get("/api/v1/messages", headers=sales_headers).json()["items"]
    assert len(mine) == len(TEXTS)
    # 未映射到自己的其他会话对 sales 不可见
    ingest(
        client,
        [
            msg(
                svr_id="x1",
                session={"wx_id": "g9@chatroom", "type": "group", "name": "别家群"},
                content="别的客户消息",
            )
        ],
    )
    mine2 = client.get("/api/v1/messages", headers=sales_headers).json()["items"]
    assert len(mine2) == len(TEXTS)
