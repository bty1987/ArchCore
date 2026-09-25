"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    token: str
    role: str
    display_name: str


class MeOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class CustomerIn(BaseModel):
    name: str
    industry: str = ""
    stage: str = "contact"
    owner_user_id: int | None = None


class CustomerOut(BaseModel):
    id: int
    name: str
    industry: str
    stage: str
    owner_user_id: int | None
    health_score: float | None
    health_level: str | None
    session_count: int = 0
    last_msg_at: datetime | None = None

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: int
    wx_id: str
    type: str
    name: str
    customer_id: int | None
    customer_name: str | None = None
    last_msg_at: datetime | None
    status: str
    message_count: int = 0


class SessionMapIn(BaseModel):
    customer_id: int | None = None  # None = 解除映射


class ClaimIn(BaseModel):
    session_ids: list[int]


class MessageOut(BaseModel):
    id: int
    session_id: int
    svr_id: str | None = None
    sender_wxid: str | None
    sender_type: str
    msg_type: str
    content: str
    media_meta: dict | None
    ts: datetime
    recalled: bool
    source: str
    tags: list[str] = []

    model_config = {"from_attributes": True}


class Page(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    total_estimate: int | None = None


class IngestMessageIn(BaseModel):
    session: dict[str, str]  # {wx_id, type, name}
    svr_id: str | None = None
    sender_wxid: str | None = None
    msg_type: str = "text"
    content: str = ""
    ts: datetime
    source: str = "decrypt"
    recalled: bool = False
    media_meta: dict | None = None
    raw: dict | None = None


class IngestBatchIn(BaseModel):
    schema_ver: int = 1
    messages: list[IngestMessageIn] = Field(max_length=500)


class IngestBatchOut(BaseModel):
    inserted: int
    skipped: int


class SyncTaskIn(BaseModel):
    type: str
    status: str
    stats: dict = {}
    log: str = ""


class AlertOut(BaseModel):
    id: int
    rule_code: str
    level: str
    status: str
    customer_id: int | None
    session_id: int | None
    message_id: int | None
    detail: dict
    handle_note: str
    created_at: datetime
    handled_at: datetime | None

    model_config = {"from_attributes": True}


class AlertHandleIn(BaseModel):
    action: str  # handled / ignored
    note: str = ""


class AlertRuleIn(BaseModel):
    code: str
    params: dict = {}
    level: str = "yellow"
    enabled: bool = True
    cooldown_minutes: int = 60


class NotifyChannelIn(BaseModel):
    type: str  # email / wecom
    name: str
    config: dict = {}
    min_level: str = "orange"
    enabled: bool = True


class UserIn(BaseModel):
    username: str
    password: str | None = None  # 置空表示不修改
    display_name: str = ""
    role: str = "sales"
    enabled: bool = True


class MemberIn(BaseModel):
    match_type: str
    match_value: str
    display_name: str = ""


class KeywordIn(BaseModel):
    category: str  # risk / focus
    word: str
    enabled: bool = True


class SettingIn(BaseModel):
    key: str
    value: dict


class WhitelistRuleIn(BaseModel):
    wx_id: str
    stype: str = "group"  # group / dm
    name: str = ""
    note: str = ""
    enabled: bool = True


class AllowAllIn(BaseModel):
    enabled: bool


class MessageTagIn(BaseModel):
    tag: str = Field(min_length=1, max_length=32)


class SummaryIn(BaseModel):
    days: int = Field(default=7, le=90)


class InventorySessionIn(BaseModel):
    wx_id: str
    type: str = "group"
    name: str = ""


class InventoryIn(BaseModel):
    sessions: list[InventorySessionIn] = Field(default_factory=list, max_length=2000)
