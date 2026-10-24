"""AI 会话摘要（F4-6，可插拔 OpenAI 兼容接口）。

配置存 app_setting("ai")：{"api_base": "https://.../v1", "api_key": "...", "model": "..."}。
数据红线：仅向所配置的内网/私有 LLM 端点发送消息摘录；未配置时功能不可用（明确报错）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import AppSetting, ChatSession, Customer, CustomerSummary


def get_ai_settings(db: Session) -> dict | None:
    row = db.get(AppSetting, "ai")
    if not row:
        return None
    cfg = row.value or {}
    if not all(cfg.get(k) for k in ("api_base", "api_key", "model")):
        return None
    return cfg


def _call_llm(cfg: dict, system: str, user: str, timeout: int = 90, history: list | None = None) -> str:
    """调用 OpenAI 兼容 chat/completions。独立函数便于测试注入。

    history: 可选多轮上下文 [{"role": "user"|"assistant", "content": str}, ...],
    插在 system 与本轮 user 之间(AI 助手多轮对话用,调用方负责截断)。
    """
    messages = [{"role": "system", "content": system}]
    for h in history or []:
        role = h.get("role")
        content = str(h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})
    resp = httpx.post(
        f"{cfg['api_base'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {cfg['api_key']}"},
        json={
            "model": cfg["model"],
            "messages": messages,
            "temperature": 0.3,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_customer_summary(db: Session, customer_id: int, days: int = 7) -> str:
    """生成客户近 N 天会话摘要并持久化。未配置 AI 时抛 ValueError。"""
    cfg = get_ai_settings(db)
    if cfg is None:
        raise ValueError(
            "AI 未配置：请在 系统设置 中填写 api_base / api_key / model（OpenAI 兼容接口）"
        )
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ValueError("客户不存在")

    since = datetime.utcnow() - timedelta(days=days)
    sessions = db.scalars(
        select(ChatSession).where(ChatSession.customer_id == customer_id)
    ).all()
    if not sessions:
        raise ValueError("该客户暂无已归档会话")
    session_names = {s.id: (s.name or s.wx_id) for s in sessions}
    id_list = ",".join(str(s.id) for s in sessions)

    rows = db.execute(
        text(
            "SELECT session_id, sender_type, content, ts FROM message "
            f"WHERE session_id IN ({id_list}) AND ts >= :since "
            "ORDER BY ts, id LIMIT 400"
        ),
        {"since": since},
    ).all()
    if not rows:
        raise ValueError(f"该客户近 {days} 天没有已归档消息")

    lines = []
    for sid, sender_type, content, ts in rows:
        snippet = (content or "").replace("\n", " ")[:100]
        lines.append(f"[{session_names.get(sid, sid)}] {ts} ({sender_type}) {snippet}")
    transcript = "\n".join(lines)

    system = (
        "你是微信客户沟通分析助手。根据给定的客户会话记录，输出简洁的中文摘要，"
        "包含：1) 沟通概况（消息量、活跃会话）；2) 客户意向与关注点；"
        "3) 风险信号（投诉、退款、竞品等）；4) 待办与建议。使用短句列表，总长不超过 300 字。"
    )
    user = f"客户：{customer.name}\n时间范围：近 {days} 天\n会话记录：\n{transcript}"
    summary = _call_llm(cfg, system, user)

    row = db.get(CustomerSummary, customer_id)
    if row is None:
        row = CustomerSummary(customer_id=customer_id)
        db.add(row)
    row.days, row.content, row.created_at = days, summary, datetime.utcnow()
    db.commit()
    return summary


def get_customer_summary(db: Session, customer_id: int) -> CustomerSummary | None:
    return db.get(CustomerSummary, customer_id)
