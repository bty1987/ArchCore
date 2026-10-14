"""经营周报(F4-7):统计快照 + LLM 生成,推送通知渠道。

数据红线:仅向所配置的私有 LLM 端点发送统计与消息摘样,不发送全量会话。
未配置 AI 时统计部分仍可用(LLM 部分明确报错)。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Alert, AppSetting, ChatSession, Customer, Message
from . import ai as ai_svc

REPORT_SETTING_KEY = "last_period_report"


def collect_stats(db: Session, days: int = 7) -> dict:
    """近 N 天经营统计快照(无 LLM 也可用)。"""
    since = datetime.utcnow() - timedelta(days=days)
    total_msgs = (
        db.scalar(select(func.count()).select_from(Message).where(Message.ts >= since)) or 0
    )
    new_customers = (
        db.scalar(select(func.count()).select_from(Customer).where(Customer.created_at >= since))
        or 0
    )
    active_sessions = (
        db.scalar(
            select(func.count(func.distinct(Message.session_id))).where(Message.ts >= since)
        )
        or 0
    )
    top = db.execute(
        select(ChatSession.name, func.count(Message.id))
        .join(Message, Message.session_id == ChatSession.id)
        .where(Message.ts >= since)
        .group_by(ChatSession.name)
        .order_by(func.count(Message.id).desc())
        .limit(5)
    ).all()
    alerts = db.scalars(select(Alert).where(Alert.created_at >= since)).all()
    alert_stat: dict[str, int] = {}
    for a in alerts:
        alert_stat[a.rule_code] = alert_stat.get(a.rule_code, 0) + 1
    pending_alerts = sum(1 for a in alerts if a.status == "pending")
    unclaimed = (
        db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.customer_id.is_(None), ChatSession.status == "active")
        )
        or 0
    )
    risk = [a for a in alerts if a.rule_code == "risk_keyword"][:5]
    return {
        "days": days,
        "total_messages": int(total_msgs),
        "new_customers": int(new_customers),
        "active_sessions": int(active_sessions),
        "top_sessions": [{"name": n or "-", "total": int(c)} for n, c in top],
        "alerts_total": len(alerts),
        "alerts_pending": pending_alerts,
        "alerts_by_rule": alert_stat,
        "unclaimed_sessions": int(unclaimed),
        "risk_samples": [str(a.detail)[:80] for a in risk],
    }


def generate_report(db: Session, days: int = 7) -> dict:
    """生成经营周报(LLM);统计快照+最近报告持久化 app_setting。"""
    stats = collect_stats(db, days)
    cfg = ai_svc.get_ai_settings(db)
    if cfg is None:
        raise ValueError(
            "AI 未配置：请在 系统设置 中填写 api_base / api_key / model（OpenAI 兼容接口）"
        )

    system = (
        "你是企业微信客户经营分析助手。根据给定的统计快照，写给企业老板的一页经营周报，"
        "中文，包含：1) 本期概览（一段话）；2) 值得注意的客户/会话动向；"
        "3) 风险与待办（结合预警数据给出处理建议）；4) 下周建议。"
        "只使用给定数据，不要编造数字。总长不超过 400 字。"
    )
    user = f"统计区间：近 {days} 天\n统计快照(JSON)：\n{stats}"

    content = ai_svc._call_llm(cfg, system, user)
    report = {
        "content": content,
        "stats": stats,
        "days": days,
        "generated_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
    }
    row = db.get(AppSetting, REPORT_SETTING_KEY)
    if row is None:
        row = AppSetting(key=REPORT_SETTING_KEY)
    row.value = report
    db.add(row)
    db.commit()
    return report


def get_last_report(db: Session) -> dict | None:
    row = db.get(AppSetting, REPORT_SETTING_KEY)
    return row.value if row else None
