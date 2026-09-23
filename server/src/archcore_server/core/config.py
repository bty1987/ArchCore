"""应用配置：环境变量前缀 ARCHCORE_，亦可用 .env 覆盖。

红线：密钥/路径禁止写死进代码；生产部署通过环境变量或 .env 提供真实值。
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

LEVEL_ORDER = {"gray": 0, "yellow": 1, "orange": 2, "red": 3}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHCORE_", env_file=".env", extra="ignore")

    app_name: str = "ArchCore"
    env: str = "dev"
    db_url: str = "sqlite:///./data/archcore.db"
    media_dir: str = "./data/media"

    # 认证：JWT 8h；首次启动无账号时用 admin_bootstrap_password 创建 admin
    jwt_secret: str = "change-me-in-production"
    jwt_ttl_hours: int = 8
    admin_bootstrap_password: str = "admin123456"

    # 采集端独立 token（/ingest 通道）
    collector_token: str = "change-me-collector-token"
    collector_wxid: str = ""  # 采集号自身 wxid，sender_type=me 的判定依据

    # 能力开关（系统设计 D5/D6：默认关闭，关闭时不注册相关路由/不启动队列）
    wcf_enabled: bool = False
    send_enabled: bool = False

    # APScheduler 常驻任务（测试中关闭，直接调函数）
    jobs_enabled: bool = True

    log_level: str = "INFO"

    def level_ge(self, level: str, threshold: str) -> bool:
        return LEVEL_ORDER.get(level, 0) >= LEVEL_ORDER.get(threshold, 0)


_DEFAULT: Settings | None = None


def get_settings() -> Settings:
    """进程内单例；create_app 会用注入的 Settings 覆盖（测试/多环境）。"""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Settings()
    return _DEFAULT


def set_settings(settings: Settings) -> None:
    global _DEFAULT
    _DEFAULT = settings
