"""版本接口(#13):三层版本对账基准。"""


def test_version_endpoint(client):
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"app", "git", "db_revision"}
    assert isinstance(body["app"], str) and body["app"]
    # git:测试环境在仓库内应有 commit;非 git 部署为 None(两者都合法)
    assert body["git"] is None or isinstance(body["git"], str)
    # 测试库未走 alembic(TestClient create_all 建表)→ None 合法;
    # 真实部署(alembic upgrade head)必有版本号
    assert body["db_revision"] is None or isinstance(body["db_revision"], str)


def test_version_matches_pyproject(client):
    from importlib.metadata import version

    r = client.get("/api/v1/version").json()
    assert r["app"] == version("archcore-server")
