"""认证与 RBAC。"""


def test_login_ok_and_me(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    assert me.json()["username"] == "admin"


def test_login_bad_password(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_no_token_unauthorized(client):
    assert client.get("/api/v1/customers").status_code == 401


def test_sales_cannot_write(client, sales_headers):
    resp = client.post("/api/v1/customers", headers=sales_headers, json={"name": "越权客户"})
    assert resp.status_code == 403


def test_sales_scoped_customers(client, admin_headers, sales_headers):
    # admin 建两个客户：一个给 sales1，一个给 admin 自己
    c1 = client.post(
        "/api/v1/customers", headers=admin_headers, json={"name": "客户甲", "owner_user_id": 2}
    ).json()
    client.post(
        "/api/v1/customers", headers=admin_headers, json={"name": "客户乙", "owner_user_id": 1}
    )
    mine = client.get("/api/v1/customers", headers=sales_headers).json()
    assert [c["name"] for c in mine] == ["客户甲"]
    allc = client.get("/api/v1/customers", headers=admin_headers).json()
    assert len(allc) == 2
    assert c1["id"]


# ---------- 首启强制改密(P0 #9) ----------


def test_default_password_flagged_on_login(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_change_password_flow(client):
    headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123456"}
        ).json()["token"],
    }
    # 旧密码错误 → 400
    bad = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "wrong-old", "new_password": "newpass123"},
    )
    assert bad.status_code == 400

    # 相同密码 → 400
    same = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "admin123456", "new_password": "admin123456"},
    )
    assert same.status_code == 400

    # 正常改密
    ok = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "admin123456", "new_password": "brand-new-pass1"},
    )
    assert ok.status_code == 200

    # 旧密码登录失效;新密码登录且不再标记强制改密
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123456"}
        ).status_code
        == 401
    )
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "brand-new-pass1"}
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is False


def test_non_admin_user_not_flagged(client, admin_headers):
    client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"username": "sales2", "password": "shortpw", "role": "sales"},
    )
    resp = client.post("/api/v1/auth/login", json={"username": "sales2", "password": "shortpw"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False
