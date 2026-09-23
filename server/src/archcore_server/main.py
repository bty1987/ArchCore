"""应用工厂 + 生命周期：init_db → 种子数据 →（可选）APScheduler。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, customers, messages, platform, sessions
from .core.config import Settings, get_settings, set_settings
from .core.db import init_db, make_engine, make_session_factory
from .models import Keyword
from .services.alert_engine import seed_rules

log = logging.getLogger(__name__)

DEFAULT_RISK_WORDS = ["投诉", "退款", "退货", "竞品", "骗子", "曝光", "315", "工商投诉"]

DEFAULT_FOCUS_WORDS = ["报价", "合同", "签约", "下单", "预算", "招标", "验收"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    set_settings(settings)  # 注入全局单例：deps/服务层统一读这份
    logging.basicConfig(level=settings.log_level)

    engine = make_engine(settings)
    factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        with factory() as db:
            auth.bootstrap_admin(db, settings.admin_bootstrap_password)
            seed_rules(db)
            _seed_keywords(db)
        if settings.jobs_enabled:
            from .jobs import inspectors

            inspectors.start_jobs(factory)
        app.state.session_factory = factory
        yield
        if settings.jobs_enabled:
            from .jobs import inspectors

            inspectors.stop_jobs()

    app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(customers.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(messages.router, prefix="/api/v1")
    app.include_router(platform.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    # F8 发送能力：v0.2 评审决策为默认永久「只收不发」，不提供任何发送路由入口；
    # 若商业化评审推翻默认值，按《主动推送消息方案》另立 outbound 路由再行评审。

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "env": settings.env}

    return app


def _seed_keywords(db) -> None:
    from sqlalchemy import select

    if db.scalar(select(Keyword).limit(1)) is None:
        for w in DEFAULT_RISK_WORDS:
            db.add(Keyword(category="risk", word=w))
        for w in DEFAULT_FOCUS_WORDS:
            db.add(Keyword(category="focus", word=w))
        db.commit()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "archcore_server.main:app", host="0.0.0.0", port=8000, log_level=settings.log_level.lower()
    )


app = create_app()
