"""预警引擎：风险词、响应超时、冷却、巡检（沉默/不活跃/采集异常）、通知分发。"""

from datetime import datetime, timedelta

from sqlalchemy import text

from tests.conftest import app_state, ingest, msg

RISK = "这个不行，我们要投诉。"


def _setup_customer(client, admin_headers):
    c = client.post(
        "/api/v1/customers", headers=admin_headers, json={"name": "预警客户", "owner_user_id": 1}
    ).json()
    # 先产生会话（g1），再认领
    ingest(client, [msg(svr_id="seed1", sender="wxid_outside", content="项目启动")])
    sessions = client.get(
        "/api/v1/sessions", params={"claimed": False}, headers=admin_headers
    ).json()
    target = next(s for s in sessions if s["wx_id"] == "g1@chatroom")
    client.post(
        f"/api/v1/customers/{c['id']}/claim",
        headers=admin_headers,
        json={"session_ids": [target["id"]]},
    )
    return c


def test_risk_keyword_alert_and_notify(client, admin_headers):
    _setup_customer(client, admin_headers)
    ingest(client, [msg(svr_id="r1", sender="wxid_outside", content=RISK)])
    alerts = client.get(
        "/api/v1/alerts", params={"status": "pending"}, headers=admin_headers
    ).json()
    risk = [a for a in alerts if a["rule_code"] == "risk_keyword"]
    assert len(risk) == 1 and risk[0]["level"] == "red"

    # 站内通知（owner=admin uid=1）
    notes = client.get("/api/v1/notifications", headers=admin_headers).json()
    assert notes["unread"] >= 1
    assert any("风险词命中" in n["title"] for n in notes["items"])


def test_risk_keyword_cooldown(client, admin_headers):
    _setup_customer(client, admin_headers)
    ingest(
        client,
        [
            msg(svr_id="r1", sender="wxid_outside", content=RISK, ts="2026-09-01T10:00:00"),
            msg(
                svr_id="r2", sender="wxid_outside", content="我要投诉你们", ts="2026-09-01T10:10:00"
            ),
        ],
    )
    alerts = client.get("/api/v1/alerts", headers=admin_headers).json()
    risk = [a for a in alerts if a["rule_code"] == "risk_keyword"]
    assert len(risk) == 1  # 冷却窗口内第二条不重复


def test_response_timeout(client, admin_headers):
    _setup_customer(client, admin_headers)
    # 客户 9:00 提问 → 我方未回 → 客户 15:30 再次发言（跨 6.5h > 4h 阈值，均为工作时间）
    ingest(
        client,
        [
            msg(svr_id="q1", sender="wxid_outside", content="在吗", ts="2026-09-01T09:00:00"),
            msg(svr_id="q2", sender="wxid_outside", content="有人吗", ts="2026-09-01T15:30:00"),
        ],
    )
    alerts = client.get("/api/v1/alerts", headers=admin_headers).json()
    timeouts = [a for a in alerts if a["rule_code"] == "response_timeout"]
    assert len(timeouts) == 1
    assert timeouts[0]["detail"]["waited_minutes"] >= 240

    # 我方回复后再触发不会误报
    ingest(
        client,
        [
            msg(svr_id="q3", sender="wxid_collector", content="来了来了", ts="2026-09-01T15:40:00"),
            msg(svr_id="q4", sender="wxid_outside", content="好的", ts="2026-09-01T15:45:00"),
        ],
    )
    alerts2 = client.get("/api/v1/alerts", headers=admin_headers).json()
    assert len([a for a in alerts2 if a["rule_code"] == "response_timeout"]) == 1


def test_no_response_timeout_outside_work_hours(client, admin_headers):
    _setup_customer(client, admin_headers)
    # 先让种子消息获得回复（否则种子提问→夜间消息本身构成超时，属正确行为）
    ingest(
        client,
        [msg(svr_id="rp1", sender="wxid_collector", content="已回复", ts="2026-09-01T10:30:00")],
    )
    # 22:00 → 次日 06:00：非工作时间不计入，工作分钟数 0 < 240 → 不触发
    ingest(
        client,
        [
            msg(svr_id="n1", sender="wxid_outside", content="晚上好", ts="2026-09-01T22:00:00"),
            msg(svr_id="n2", sender="wxid_outside", content="早上好", ts="2026-09-02T06:00:00"),
        ],
    )
    alerts = client.get("/api/v1/alerts", headers=admin_headers).json()
    assert not [a for a in alerts if a["rule_code"] == "response_timeout"]


def test_silence_inspection(client, admin_headers):
    c = _setup_customer(client, admin_headers)
    # 客户方最后发言在 10 天前
    ingest(
        client,
        [
            msg(
                svr_id="old1",
                sender="wxid_outside",
                content="上次的消息",
                ts=(datetime.utcnow() - timedelta(days=10)).isoformat(sep=" ", timespec="seconds"),
            )
        ],
    )
    from archcore_server.services.alert_engine import silence_inspection

    db = app_state(client).session_factory()
    try:
        fired = silence_inspection(db)
        assert fired >= 1
        rows = db.execute(
            text("SELECT rule_code, customer_id FROM alert WHERE rule_code='customer_silence'")
        ).fetchall()
        assert any(row[1] == c["id"] for row in rows)
        # 冷却期内再次巡检不重复
        assert silence_inspection(db) == 0
    finally:
        db.close()


def test_collect_stale_inspection(client, admin_headers):
    from archcore_server.services.alert_engine import collect_stale_inspection

    db = app_state(client).session_factory()
    try:
        # 无任务不告警
        assert collect_stale_inspection(db) == 0
        stale = datetime.utcnow() - timedelta(hours=5)
        db.execute(
            text(
                "INSERT INTO sync_task"
                "(type,status,stats,log,collector_wxid,created_at,finished_at) "
                "VALUES('incr_sync','success','{}','','wxid_c',:c,:f)"
            ),
            {"c": stale.isoformat(sep=" "), "f": stale.isoformat(sep=" ")},
        )
        db.commit()
        assert collect_stale_inspection(db) == 1
        # 最近一次任务 failed → 立即告警（不等超时）
        db.execute(
            text("DELETE FROM sync_task"),
        )
        recent = datetime.utcnow().isoformat(sep=" ")
        db.execute(
            text(
                "INSERT INTO sync_task"
                "(type,status,stats,log,collector_wxid,created_at,finished_at) "
                "VALUES('incr_sync','failed','{}','decrypt_failed','wxid_c',:c,:f)"
            ),
            {"c": recent, "f": recent},
        )
        db.commit()
        # 清掉前一条告警模拟冷却过期（failed 心跳每 30 分钟一次，冷却 60 分钟内只报一次）
        db.execute(text("DELETE FROM notify_record"))
        db.execute(text("DELETE FROM inapp_notification"))
        db.execute(text("DELETE FROM alert"))
        db.commit()
        assert collect_stale_inspection(db) == 1  # failed 即告警
        # 恢复成功心跳后不再告警
        db.execute(text("DELETE FROM sync_task"))
        fresh = datetime.utcnow().isoformat(sep=" ")
        db.execute(
            text(
                "INSERT INTO sync_task"
                "(type,status,stats,log,collector_wxid,created_at,finished_at) "
                "VALUES('incr_sync','success','{}','','wxid_c',:c,:f)"
            ),
            {"c": fresh, "f": fresh},
        )
        db.commit()
        assert collect_stale_inspection(db) == 0
    finally:
        db.close()


def test_alert_handle_and_audit(client, admin_headers):
    _setup_customer(client, admin_headers)
    ingest(client, [msg(svr_id="r9", sender="wxid_outside", content=RISK)])
    alert = client.get(
        "/api/v1/alerts", params={"status": "pending"}, headers=admin_headers
    ).json()[0]
    resp = client.post(
        f"/api/v1/alerts/{alert['id']}/handle",
        headers=admin_headers,
        json={"action": "handled", "note": "已电话安抚"},
    )
    assert resp.json()["status"] == "handled"
    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    assert any(e["action"] == "alert_handle" for e in logs)
