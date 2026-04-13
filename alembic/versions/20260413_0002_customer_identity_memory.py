"""customer identity and key memories

Revision ID: 20260413_0002
Revises: 20260403_0001
Create Date: 2026-04-13 13:00:00
"""

from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260413_0002"
down_revision = "20260403_0001"
branch_labels = None
depends_on = None


def _generate_customer_id() -> str:
    return f"CUST-{uuid4().hex[:12].upper()}"


def _normalize_phone(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or raw


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("contacts", sa.Column("customer_id", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_contacts_customer_id"), "contacts", ["customer_id"], unique=True)

    existing_contacts = bind.execute(sa.text("SELECT id FROM contacts")).mappings().all()
    for row in existing_contacts:
        bind.execute(
            sa.text("UPDATE contacts SET customer_id = :customer_id WHERE id = :contact_id"),
            {
                "customer_id": _generate_customer_id(),
                "contact_id": row["id"],
            },
        )

    with op.batch_alter_table("contacts") as batch_op:
        batch_op.alter_column("customer_id", nullable=False)

    op.create_table(
        "contact_identities",
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("platform_user_id", sa.String(length=255), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_contact_identities_contact_id_contacts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_identities")),
        sa.UniqueConstraint("platform", "platform_user_id", name="uq_contact_identities_platform_platform_user_id"),
    )
    op.create_index(op.f("ix_contact_identities_contact_id"), "contact_identities", ["contact_id"], unique=False)
    op.create_index(op.f("ix_contact_identities_platform"), "contact_identities", ["platform"], unique=False)
    op.create_index(
        op.f("ix_contact_identities_platform_user_id"),
        "contact_identities",
        ["platform_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_identities_normalized_value"),
        "contact_identities",
        ["normalized_value"],
        unique=False,
    )

    op.create_table(
        "contact_memories",
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("memory_key", sa.String(length=100), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_contact_memories_contact_id_contacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["messages.id"],
            name=op.f("fk_contact_memories_source_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_memories")),
        sa.UniqueConstraint("contact_id", "memory_key", name="uq_contact_memories_contact_id_memory_key"),
    )
    op.create_index(op.f("ix_contact_memories_contact_id"), "contact_memories", ["contact_id"], unique=False)
    op.create_index(op.f("ix_contact_memories_memory_key"), "contact_memories", ["memory_key"], unique=False)
    op.create_index(op.f("ix_contact_memories_source_message_id"), "contact_memories", ["source_message_id"], unique=False)
    op.create_index(op.f("ix_contact_memories_status"), "contact_memories", ["status"], unique=False)

    existing_contact_rows = bind.execute(
        sa.text(
            """
            SELECT id, phone, instagram_user_id, tiktok_user_id, youtube_channel_id
            FROM contacts
            """
        )
    ).mappings().all()
    contact_identities_table = sa.table(
        "contact_identities",
        sa.column("id", sa.Uuid()),
        sa.column("contact_id", sa.Uuid()),
        sa.column("platform", sa.String(length=50)),
        sa.column("platform_user_id", sa.String(length=255)),
        sa.column("normalized_value", sa.String(length=255)),
        sa.column("is_primary", sa.Boolean()),
        sa.column("metadata_json", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    def insert_identity(*, contact_id, platform: str, value: str | None) -> None:
        raw = str(value or "").strip()
        if not raw:
            return
        normalized = _normalize_phone(raw) if platform == "whatsapp" else raw.lower()
        existing = bind.execute(
            sa.text(
                """
                SELECT id
                FROM contact_identities
                WHERE platform = :platform AND platform_user_id = :platform_user_id
                LIMIT 1
                """
            ),
            {"platform": platform, "platform_user_id": normalized},
        ).first()
        if existing is not None:
            return

        now_utc = datetime.now(timezone.utc)
        bind.execute(
            sa.insert(contact_identities_table).values(
                id=uuid4(),
                contact_id=contact_id,
                platform=platform,
                platform_user_id=normalized,
                normalized_value=normalized,
                is_primary=False,
                metadata_json={},
                created_at=now_utc,
                updated_at=now_utc,
            ),
        )

    for row in existing_contact_rows:
        contact_id = row["id"]
        insert_identity(contact_id=contact_id, platform="whatsapp", value=row.get("phone"))
        insert_identity(contact_id=contact_id, platform="instagram", value=row.get("instagram_user_id"))
        insert_identity(contact_id=contact_id, platform="tiktok", value=row.get("tiktok_user_id"))
        insert_identity(contact_id=contact_id, platform="youtube", value=row.get("youtube_channel_id"))


def downgrade() -> None:
    op.drop_index(op.f("ix_contact_memories_status"), table_name="contact_memories")
    op.drop_index(op.f("ix_contact_memories_source_message_id"), table_name="contact_memories")
    op.drop_index(op.f("ix_contact_memories_memory_key"), table_name="contact_memories")
    op.drop_index(op.f("ix_contact_memories_contact_id"), table_name="contact_memories")
    op.drop_table("contact_memories")

    op.drop_index(op.f("ix_contact_identities_normalized_value"), table_name="contact_identities")
    op.drop_index(op.f("ix_contact_identities_platform_user_id"), table_name="contact_identities")
    op.drop_index(op.f("ix_contact_identities_platform"), table_name="contact_identities")
    op.drop_index(op.f("ix_contact_identities_contact_id"), table_name="contact_identities")
    op.drop_table("contact_identities")

    op.drop_index(op.f("ix_contacts_customer_id"), table_name="contacts")
    op.drop_column("contacts", "customer_id")
