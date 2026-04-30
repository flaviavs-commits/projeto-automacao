"""menu bot collection state persistence

Revision ID: 20260430_0006
Revises: 20260430_0005
Create Date: 2026-04-30 19:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260430_0006"
down_revision = "20260430_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = str(bind.dialect.name or "").lower()

    op.add_column(
        "conversations",
        sa.Column(
            "customer_collection_data",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column("conversations", sa.Column("customer_collection_step", sa.String(length=80), nullable=True))
    op.create_index(
        op.f("ix_conversations_customer_collection_step"),
        "conversations",
        ["customer_collection_step"],
        unique=False,
    )

    if dialect_name != "sqlite":
        op.alter_column("conversations", "customer_collection_data", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_conversations_customer_collection_step"), table_name="conversations")
    op.drop_column("conversations", "customer_collection_step")
    op.drop_column("conversations", "customer_collection_data")
