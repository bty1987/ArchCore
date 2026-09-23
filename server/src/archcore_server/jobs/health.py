"""健康度模型（F4-4）：score = w1·活跃 + w2·响应达标 + w3·沉默 + w4·风险。

默认权重 60/20/10/10，存 app_setting(health_weights) 可调；输出 0-100 + 红/黄/绿
写入 customer 冗余字段（score < 40 红，< 70 黄，其余绿）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from ..models import Alert, ChatSession, Customer, Message, MessageDaily
from ..services import analysis

log = logging.getLogger(__name__)

WEIGHTS_DEFAULT = {"activity": 60, "response": 20, "silence": 10, "risk": 10}


def get_weights(db) -> dict:
    from ..models import AppSetting

    row = db.get(AppSetting, "health_weights")
    return row.value if row else WEIGHTS_DEFAULT


def _sum_days(db, session_ids: list[int], days: int) -> float:
    return float(
        db.scalar(
            select(func.coalesce(func.sum(MessageDaily.total), 0)).where(
                MessageDaily.session_id.in_(session_ids),
                MessageDaily.date >= (date.today() - timedelta(days=days)).isoformat(),
            )
        )
        or 0
    )


def recompute_health(db, weights: dict | None = None) -> int:
    weights = weights or WEIGHTS_DEFAULT
    w_act, w_resp, w_sil, w_risk = (
        weights.get("activity", 60),
        weights.get("response", 20),
        weights.get("silence", 10),
        weights.get("risk", 10),
    )
    now = datetime.utcnow()
    count = 0
    for c in db.scalars(select(Customer)).all():
        session_ids = [
            sid for sid in db.scalars(select(ChatSession.id).where(ChatSession.customer_id == c.id))
        ]
        if not session_ids:
            continue

        # 活跃度：近 14 天日均消息量，日均 2 条 = 100 分封顶
        total14 = _sum_days(db, session_ids, 14)
        activity = min(100.0, total14 / 14 / 2 * 100)

        # 响应：近 14 天客户方发言的我方 4h（工作时间口径）回复达标率；无数据给中性 60
        lats: list[int] = []
        for sid in session_ids:
            lats.extend(analysis.compute_reply_latencies(db, sid, days=14))
        response = (len([x for x in lats if 0 <= x <= 240]) / len(lats) * 100) if lats else 60.0

        # 沉默：最后一次客户方发言距今（<=7 天满，7-14 天半，>14 天零）
        last_ext = db.scalar(
            select(Message.ts)
            .where(Message.session_id.in_(session_ids), Message.sender_type == "external")
            .order_by(Message.ts.desc())
            .limit(1)
        )
        if last_ext is None:
            silence = 50.0
        else:
            d = (now - last_ext).days
            silence = 100.0 if d <= 7 else (50.0 if d <= 14 else 0.0)

        # 风险：近 30 天红预警每个 -20、橙预警每个 -5
        red = _alert_count(db, c.id, "red", now)
        orange = _alert_count(db, c.id, "orange", now)
        risk = max(0.0, 100.0 - red * 20 - orange * 5)

        score = round(
            (activity * w_act + response * w_resp + silence * w_sil + risk * w_risk)
            / (w_act + w_resp + w_sil + w_risk),
            1,
        )
        c.health_score = score
        c.health_level = "red" if score < 40 else ("yellow" if score < 70 else "green")
        count += 1
    db.commit()
    return count


def _alert_count(db, customer_id: int, level: str, now: datetime) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.customer_id == customer_id,
                Alert.level == level,
                Alert.created_at >= now - timedelta(days=30),
            )
        )
        or 0
    )


def run(factory) -> int:
    with factory() as db:
        n = recompute_health(db, get_weights(db))
        log.info("health recompute customers=%s", n)
        return n
