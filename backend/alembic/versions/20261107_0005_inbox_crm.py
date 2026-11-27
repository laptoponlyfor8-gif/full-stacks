"""Add tenant-scoped contacts and CRM data; link stored messages to contacts."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0005"
down_revision: str | None = "20261107_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


TENANT_POLICY = (
    "organization_id = "
    "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
)


def _enable_tenant_isolation(tables: tuple[str, ...]) -> None:
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({TENANT_POLICY}) WITH CHECK ({TENANT_POLICY})"
        )


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("social_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_customer_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=200), server_default="", nullable=False),
        sa.Column("lead_status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column(
            "custom_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("first_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_contacts_org_social_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contacts"),
        sa.UniqueConstraint("organization_id", "id", name="uq_contacts_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "social_account_id",
            "platform_customer_id",
            name="uq_contacts_org_account_platform_customer",
        ),
    )
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])
    op.create_index("ix_contacts_social_account_id", "contacts", ["social_account_id"])
    op.create_index(
        "ix_contacts_org_status_updated",
        "contacts",
        ["organization_id", "lead_status", "updated_at"],
    )
    op.create_index(
        "ix_contacts_org_last_interaction",
        "contacts",
        ["organization_id", "last_interaction_at"],
    )
    op.create_index("ix_contacts_created_at", "contacts", ["created_at"])

    op.create_table(
        "contact_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_contact_notes_org_contact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name="fk_contact_notes_author_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contact_notes"),
    )
    op.create_index("ix_contact_notes_organization_id", "contact_notes", ["organization_id"])
    op.create_index(
        "ix_contact_notes_org_contact_created",
        "contact_notes",
        ["organization_id", "contact_id", "created_at"],
    )
    op.create_index("ix_contact_notes_created_at", "contact_notes", ["created_at"])

    op.create_table(
        "contact_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_contact_tags_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contact_tags"),
        sa.UniqueConstraint("organization_id", "id", name="uq_contact_tags_org_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_contact_tags_org_name"),
    )
    op.create_index("ix_contact_tags_organization_id", "contact_tags", ["organization_id"])
    op.create_index("ix_contact_tags_created_at", "contact_tags", ["created_at"])

    op.create_table(
        "contact_tag_assignments",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_contact_tag_assignments_org_contact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "tag_id"],
            ["contact_tags.organization_id", "contact_tags.id"],
            name="fk_contact_tag_assignments_org_tag",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "contact_id", "tag_id", name="pk_contact_tag_assignments"
        ),
    )
    op.create_index(
        "ix_contact_tag_assignments_org_tag",
        "contact_tag_assignments",
        ["organization_id", "tag_id"],
    )
    op.create_index(
        "ix_contact_tag_assignments_created_at",
        "contact_tag_assignments",
        ["created_at"],
    )

    op.create_table(
        "lead_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_type", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_lead_activities_org_contact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_lead_activities_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lead_activities"),
    )
    op.create_index("ix_lead_activities_organization_id", "lead_activities", ["organization_id"])
    op.create_index(
        "ix_lead_activities_org_contact_created",
        "lead_activities",
        ["organization_id", "contact_id", "created_at"],
    )
    op.create_index("ix_lead_activities_created_at", "lead_activities", ["created_at"])

    op.add_column(
        "messages",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("platform_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.execute(
        """
        INSERT INTO contacts (
            id, organization_id, social_account_id, platform_customer_id,
            display_name, lead_status, custom_fields, first_contact_at,
            last_interaction_at
        )
        SELECT gen_random_uuid(), organization_id, social_account_id,
               recipient_platform_id, '', 'new', '{}'::jsonb,
               MIN(created_at), MAX(created_at)
        FROM messages
        WHERE recipient_platform_id <> ''
        GROUP BY organization_id, social_account_id, recipient_platform_id
        """
    )
    op.execute(
        """
        UPDATE messages AS m
        SET contact_id = c.id
        FROM contacts AS c
        WHERE m.organization_id = c.organization_id
          AND m.social_account_id = c.social_account_id
          AND m.recipient_platform_id = c.platform_customer_id
        """
    )
    op.create_foreign_key(
        "fk_messages_org_contact",
        "messages",
        "contacts",
        ["organization_id", "contact_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_messages_org_contact_created",
        "messages",
        ["organization_id", "contact_id", "created_at"],
    )
    op.create_index("ix_messages_contact_id", "messages", ["contact_id"])

    _enable_tenant_isolation(
        ("contacts", "contact_notes", "contact_tags", "contact_tag_assignments", "lead_activities")
    )


def downgrade() -> None:
    for table in ("lead_activities", "contact_tag_assignments", "contact_tags", "contact_notes", "contacts"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index("ix_messages_contact_id", table_name="messages")
    op.drop_index("ix_messages_org_contact_created", table_name="messages")
    op.drop_constraint("fk_messages_org_contact", "messages", type_="foreignkey")
    op.drop_column("messages", "is_read")
    op.drop_column("messages", "platform_created_at")
    op.drop_column("messages", "contact_id")
    op.drop_table("lead_activities")
    op.drop_table("contact_tag_assignments")
    op.drop_table("contact_tags")
    op.drop_table("contact_notes")
    op.drop_table("contacts")
