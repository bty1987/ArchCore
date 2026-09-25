"""whitelist_rule 表（白名单页面化）

Revision ID: a1b7c3d9e5f1
Revises: 93500a469fc8
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a1b7c3d9e5f1"
down_revision = "93500a469fc8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whitelist_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wx_id", sa.String(length=128), nullable=False),
        sa.Column("stype", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("note", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wx_id"),
    )


def downgrade() -> None:
    op.drop_table("whitelist_rule")
