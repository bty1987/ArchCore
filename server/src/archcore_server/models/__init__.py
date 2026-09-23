"""SQLAlchemy 模型 —— 唯一 schema 源。变更一律走 alembic 迁移，禁止手改库。

时间口径：ts 取微信原始时间戳（本地 naive datetime）；created_at 为入库时间。
去重：svr_id 第一优先（微信原生 MsgSvrID），fingerprint 兜底（仅 server 端算，见 services/ingest）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _dt() -> Mapped[datetime]:
    return mapped_column(DateTime, default=datetime.utcnow)


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16))  # admin / manager / sales
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _dt()


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    industry: Mapped[str] = mapped_column(String(64), default="")
    stage: Mapped[str] = mapped_column(String(16), default="contact")  # 接触/方案/报价/成交/售后
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    health_level: Mapped[str | None] = mapped_column(String(8), nullable=True)  # red/yellow/green
    created_at: Mapped[datetime] = _dt()


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    wx_id: Mapped[str] = mapped_column(String(128), unique=True)
    type: Mapped[str] = mapped_column(String(8))  # group / dm
    name: Mapped[str] = mapped_column(String(128), default="")
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id"), nullable=True
    )  # 空 = 待认领
    last_msg_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / archived
    created_at: Mapped[datetime] = _dt()


class Contact(Base):
    __tablename__ = "contact"

    id: Mapped[int] = mapped_column(primary_key=True)
    wx_id: Mapped[str] = mapped_column(String(128), unique=True)
    nickname: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(String(128), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)


class Member(Base):
    """内部成员名单（F2-4）：sender_type 判定依据。"""

    __tablename__ = "member"
    __table_args__ = (UniqueConstraint("match_type", "match_value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_type: Mapped[str] = mapped_column(String(16))  # wxid / nickname / remark
    match_value: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(64), default="")


class GroupMemberSnap(Base):
    """群成员快照（F2-5，依赖 WCF 轨）：退群预警输入。"""

    __tablename__ = "group_member_snap"
    __table_args__ = (Index("ix_gms_session", "session_id", "wx_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_session.id"))
    wx_id: Mapped[str] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = _dt()
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("ix_message_session_ts", "session_id", "ts"),
        Index("ix_message_sender_type", "sender_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_session.id"))
    svr_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    sender_wxid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sender_type: Mapped[str] = mapped_column(String(8))  # external / internal / me / system
    msg_type: Mapped[str] = mapped_column(
        String(16)
    )  # text/image/video/voice/file/quote/emoji/system
    content: Mapped[str] = mapped_column(Text, default="")
    media_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    media_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    recalled: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(8), default="decrypt")  # decrypt / wcf
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _dt()


class MessageDaily(Base):
    """日聚合表：仪表盘与趋势图直接读此表，不扫 message（设计决策 D7）。"""

    __tablename__ = "message_daily"
    __table_args__ = (UniqueConstraint("session_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_session.id"))
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    total: Mapped[int] = mapped_column(Integer, default=0)
    ext_count: Mapped[int] = mapped_column(Integer, default=0)
    int_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_latencies: Mapped[list | None] = mapped_column(JSON, nullable=True)  # 分钟列表


class AlertRule(Base):
    __tablename__ = "alert_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    level: Mapped[str] = mapped_column(String(8), default="yellow")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (Index("ix_alert_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_session.id"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("message.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(8), default="pending")  # pending/handled/ignored
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    handle_note: Mapped[str] = mapped_column(Text, default="")
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    created_at: Mapped[datetime] = _dt()
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotifyChannel(Base):
    __tablename__ = "notify_channel"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(16))  # inapp / email / wecom
    name: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # webhook_url / smtp 等
    min_level: Mapped[str] = mapped_column(String(8), default="orange")  # 达到该级别才外发
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NotifyRecord(Base):
    __tablename__ = "notify_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alert.id"))
    channel: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(16))  # sent / failed / skipped
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _dt()


class InAppNotification(Base):
    """站内通知（F6-1）：铃铛未读数数据源。"""

    __tablename__ = "inapp_notification"
    __table_args__ = (Index("ix_inapp_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alert.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text, default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = _dt()


class Keyword(Base):
    __tablename__ = "keyword"
    __table_args__ = (UniqueConstraint("category", "word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(8))  # risk / focus
    word: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SyncTask(Base):
    __tablename__ = "sync_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))  # full_import / incr_sync / wcf
    status: Mapped[str] = mapped_column(String(16))  # running / success / failed
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    log: Mapped[str] = mapped_column(Text, default="")
    collector_wxid: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = _dt()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = _dt()


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
