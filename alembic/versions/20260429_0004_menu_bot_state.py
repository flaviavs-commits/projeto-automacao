"""menu bot state and human handoff fields

Revision ID: 20260429_0004
Revises: 20260429_0003
Create Date: 2026-04-29 12:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_0004"
down_revision = "20260429_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = str(bind.dialect.name or "").lower()

    op.add_column("conversations", sa.Column("menu_state", sa.String(length=80), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("needs_human", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("conversations", sa.Column("human_reason", sa.String(length=120), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("human_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_conversations_menu_state"), "conversations", ["menu_state"], unique=False)
    op.create_index(op.f("ix_conversations_needs_human"), "conversations", ["needs_human"], unique=False)
    op.create_index(
        op.f("ix_conversations_human_requested_at"),
        "conversations",
        ["human_requested_at"],
        unique=False,
    )
    if dialect_name != "sqlite":
        op.alter_column("conversations", "needs_human", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_conversations_human_requested_at"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_needs_human"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_menu_state"), table_name="conversations")
    op.drop_column("conversations", "human_requested_at")
    op.drop_column("conversations", "human_reason")
    op.drop_column("conversations", "needs_human")
    op.drop_column("conversations", "menu_state")
