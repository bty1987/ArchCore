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
