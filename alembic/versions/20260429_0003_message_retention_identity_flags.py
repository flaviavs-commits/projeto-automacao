"""message retention and temporary identity fields

Revision ID: 20260429_0003
Revises: 20260413_0002
Create Date: 2026-04-29 09:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_0003"
down_revision = "20260413_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = str(bind.dialect.name or "").lower()

    op.add_column(
        "contacts",
        sa.Column("is_temporary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(op.f("ix_contacts_is_temporary"), "contacts", ["is_temporary"], unique=False)
    if dialect_name != "sqlite":
        op.alter_column("contacts", "is_temporary", server_default=None)

    op.add_column("conversations", sa.Column("last_inbound_message_text", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("last_inbound_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_conversations_last_inbound_message_at"),
        "conversations",
        ["last_inbound_message_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_conversations_last_inbound_message_at"), table_name="conversations")
    op.drop_column("conversations", "last_inbound_message_at")
    op.drop_column("conversations", "last_inbound_message_text")

    op.drop_index(op.f("ix_contacts_is_temporary"), table_name="contacts")
    op.drop_column("contacts", "is_temporary")
