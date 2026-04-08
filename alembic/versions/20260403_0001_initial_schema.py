"""initial schema

Revision ID: 20260403_0001
Revises:
Create Date: 2026-04-03 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260403_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_entity_type"), "audit_logs", ["entity_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_event_type"), "audit_logs", ["event_type"], unique=False)

    op.create_table(
        "contacts",
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("instagram_user_id", sa.String(length=255), nullable=True),
        sa.Column("youtube_channel_id", sa.String(length=255), nullable=True),
        sa.Column("tiktok_user_id", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index(op.f("ix_contacts_email"), "contacts", ["email"], unique=False)
    op.create_index(op.f("ix_contacts_instagram_user_id"), "contacts", ["instagram_user_id"], unique=False)
    op.create_index(op.f("ix_contacts_phone"), "contacts", ["phone"], unique=False)
    op.create_index(op.f("ix_contacts_tiktok_user_id"), "contacts", ["tiktok_user_id"], unique=False)
    op.create_index(op.f("ix_contacts_youtube_channel_id"), "contacts", ["youtube_channel_id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"], unique=False)

    op.create_table(
        "platform_accounts",
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("access_token_encrypted", sa.String(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.String(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_accounts")),
    )
    op.create_index(op.f("ix_platform_accounts_external_account_id"), "platform_accounts", ["external_account_id"], unique=False)
    op.create_index(op.f("ix_platform_accounts_platform"), "platform_accounts", ["platform"], unique=False)

    op.create_table(
        "posts",
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("media_url", sa.String(length=500), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_post_id", sa.String(length=255), nullable=True),
        sa.Column("platform_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
    )
    op.create_index(op.f("ix_posts_external_post_id"), "posts", ["external_post_id"], unique=False)
    op.create_index(op.f("ix_posts_platform"), "posts", ["platform"], unique=False)

    op.create_table(
        "conversations",
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], name=op.f("fk_conversations_contact_id_contacts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(op.f("ix_conversations_contact_id"), "conversations", ["contact_id"], unique=False)
    op.create_index(op.f("ix_conversations_last_message_at"), "conversations", ["last_message_at"], unique=False)
    op.create_index(op.f("ix_conversations_platform"), "conversations", ["platform"], unique=False)

    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("transcription", sa.Text(), nullable=True),
        sa.Column("media_url", sa.String(length=500), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("ai_generated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], name=op.f("fk_messages_conversation_id_conversations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_messages_external_message_id"), "messages", ["external_message_id"], unique=False)
    op.create_index(op.f("ix_messages_platform"), "messages", ["platform"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_platform"), table_name="messages")
    op.drop_index(op.f("ix_messages_external_message_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_conversations_platform"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_last_message_at"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_contact_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_posts_platform"), table_name="posts")
    op.drop_index(op.f("ix_posts_external_post_id"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_platform_accounts_platform"), table_name="platform_accounts")
    op.drop_index(op.f("ix_platform_accounts_external_account_id"), table_name="platform_accounts")
    op.drop_table("platform_accounts")
    op.drop_index(op.f("ix_jobs_job_type"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_contacts_youtube_channel_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_tiktok_user_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_phone"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_instagram_user_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_email"), table_name="contacts")
    op.drop_table("contacts")
    op.drop_index(op.f("ix_audit_logs_event_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
