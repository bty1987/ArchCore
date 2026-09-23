"""alembic 环境：schema 唯一源 = archcore_server.models.Base.metadata。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import pool

from alembic import context

# 保证可导入 src/archcore_server（未安装 editable 时）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from archcore_server.models import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _db_url() -> str:
    return os.environ.get("ARCHCORE_DB_URL", "sqlite:///./data/archcore.db")


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connectable = create_engine(_db_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 变更列需 batch 模式
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
