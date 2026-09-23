"""server 测试公共夹具：临时库 + TestClient + 登录辅助。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVER_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SERVER_SRC))

from archcore_server.core.config import Settings  # noqa: E402
from archcore_server.main import create_app  # noqa: E402


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        db_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        media_dir=str(tmp_path / "media"),
        jwt_secret="test-secret",
        collector_token="test-collector-token",
        collector_wxid="wxid_collector",
        jobs_enabled=False,
        admin_bootstrap_password="admin123456",
    )


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def sales_headers(client, admin_headers):
    """创建一个 sales 用户及其负责的客户。"""
    client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": "sales1",
            "password": "sales123",
            "display_name": "销售一号",
            "role": "sales",
            "enabled": True,
        },
    )
    resp = client.post("/api/v1/auth/login", json={"username": "sales1", "password": "sales123"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def app_state(client):
    """拿 app.state（session_factory 所在）。"""
    return client.app.state


def ingest(client, messages: list[dict]):
    return client.post(
        "/api/v1/ingest/messages",
        json={"schema_ver": 1, "messages": messages},
        headers={"X-Collector-Token": "test-collector-token"},
    )


def msg(
    svr_id=None,
    sender=None,
    content="hello",
    ts="2026-09-01T10:00:00",
    msg_type="text",
    session=None,
    **kw,
):
    session = session or {"wx_id": "g1@chatroom", "type": "group", "name": "测试群"}
    d = {
        "session": session,
        "svr_id": svr_id,
        "sender_wxid": sender,
        "msg_type": msg_type,
        "content": content,
        "ts": ts,
        "source": "decrypt",
    }
    d.update(kw)
    return d
