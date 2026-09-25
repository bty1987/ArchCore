"""message_tag 与 customer_summary（标注 F3-4 / AI 摘要 F4-6）

Revision ID: c5e7a9b1d3f5
Revises: a1b7c3d9e5f1
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c5e7a9b1d3f5"
down_revision = "a1b7c3d9e5f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["message.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "tag"),
    )
    op.create_table(
        "customer_summary",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id"),
    )


def downgrade() -> None:
    op.drop_table("customer_summary")
    op.drop_table("message_tag")
