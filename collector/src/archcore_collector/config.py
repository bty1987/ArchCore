"""采集端配置：YAML + 环境变量（ARCHCORE_COLLECTOR_ 前缀）覆盖。

红线：config.yaml 含 token，不入 git（example 入库）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhitelistConfig(BaseModel):
    """会话白名单（F1-6 合规边界）：非白名单会话在采集端被过滤，数据不出微信目录。

    allow_all 仅限个人本机测试环境：放宽白名单采集全部已同步会话，便于功能验证。
    商用部署禁止开启（数据最小化是合规方案的硬要求）。
    """

    groups: list[str] = []  # 群 wx_id 精确名单
    group_name_patterns: list[str] = []  # 群名正则（如 ^ABC项目）
    allow_dm: bool = True  # 是否采集采集号自身的客户单聊
    allow_all: bool = False  # 测试开关：忽略白名单，采集全部（个人本机测试专用）


class SourceConfig(BaseModel):
    type: str = "fixture"  # fixture / pywxdump
    db_dir: str = ""  # 微信解密库目录（pywxdump 模式）
    fixture_path: str = ""  # fixture 模式的样本库路径


class ScheduleConfig(BaseModel):
    incr_minutes: int = 60
    flush_seconds: int = 30


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHCORE_COLLECTOR_", extra="ignore")

    server_base_url: str = "http://127.0.0.1:8000"
    server_ingest_token: str = "change-me-collector-token"
    collector_wxid: str = ""  # 采集号自身 wxid
    state_db: str = "./data/collector_state.db"
    source: SourceConfig = Field(default_factory=SourceConfig)
    whitelist: WhitelistConfig = Field(default_factory=WhitelistConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    batch_size: int = 500
    wcf_enabled: bool = False  # 实时轨开关（依赖 M0 验证）
    send_enabled: bool = False  # 永久 False：归档系统只收不发


def load_config(path: str | Path | None = None) -> CollectorSettings:
    """加载顺序：默认值 ← YAML ← 环境变量。"""
    data: dict = {}
    if path is None:
        candidate = Path("config.yaml")
        path = candidate if candidate.exists() else None
    if path is not None:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if loaded:
            data = loaded
    return CollectorSettings(**data)
