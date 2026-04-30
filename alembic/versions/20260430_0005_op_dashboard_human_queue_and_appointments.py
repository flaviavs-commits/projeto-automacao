"""op dashboard human queue controls and appointments

Revision ID: 20260430_0005
Revises: 20260429_0004
Create Date: 2026-04-30 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260430_0005"
down_revision = "20260429_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = str(bind.dialect.name or "").lower()

    op.add_column(
        "conversations",
        sa.Column("human_status", sa.String(length=30), nullable=False, server_default="closed"),
    )
    op.add_column("conversations", sa.Column("human_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("human_accepted_by", sa.String(length=120), nullable=True))
    op.add_column("conversations", sa.Column("human_ignored_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("human_ignored_by", sa.String(length=120), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("chatbot_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(op.f("ix_conversations_human_status"), "conversations", ["human_status"], unique=False)
    op.create_index(op.f("ix_conversations_human_accepted_at"), "conversations", ["human_accepted_at"], unique=False)
    op.create_index(op.f("ix_conversations_human_ignored_at"), "conversations", ["human_ignored_at"], unique=False)
    op.create_index(op.f("ix_conversations_chatbot_enabled"), "conversations", ["chatbot_enabled"], unique=False)

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("customer_phone", sa.String(length=50), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], name=op.f("fk_appointments_contact_id_contacts"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_appointments_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
    )
    op.create_index(op.f("ix_appointments_contact_id"), "appointments", ["contact_id"], unique=False)
    op.create_index(op.f("ix_appointments_conversation_id"), "appointments", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_appointments_customer_name"), "appointments", ["customer_name"], unique=False)
    op.create_index(op.f("ix_appointments_customer_phone"), "appointments", ["customer_phone"], unique=False)
    op.create_index(op.f("ix_appointments_start_time"), "appointments", ["start_time"], unique=False)
    op.create_index(op.f("ix_appointments_end_time"), "appointments", ["end_time"], unique=False)
    op.create_index(op.f("ix_appointments_status"), "appointments", ["status"], unique=False)

    if dialect_name != "sqlite":
        op.alter_column("conversations", "human_status", server_default=None)
        op.alter_column("conversations", "chatbot_enabled", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_appointments_status"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_end_time"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_start_time"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_customer_phone"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_customer_name"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_conversation_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_contact_id"), table_name="appointments")
    op.drop_table("appointments")

    op.drop_index(op.f("ix_conversations_chatbot_enabled"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_human_ignored_at"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_human_accepted_at"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_human_status"), table_name="conversations")
    op.drop_column("conversations", "chatbot_enabled")
    op.drop_column("conversations", "human_ignored_by")
    op.drop_column("conversations", "human_ignored_at")
    op.drop_column("conversations", "human_accepted_by")
    op.drop_column("conversations", "human_accepted_at")
    op.drop_column("conversations", "human_status")
