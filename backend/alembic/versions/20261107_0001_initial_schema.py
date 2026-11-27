"""Create the initial multi-tenant database schema.

Revision ID: 20261107_0001
Revises:
Create Date: 2026-11-07
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE organization_role AS ENUM ('owner', 'admin', 'member')")
    op.execute("CREATE TYPE social_platform AS ENUM ('instagram', 'facebook')")
    op.execute(
        "CREATE TYPE automation_status AS ENUM "
        "('draft', 'active', 'paused', 'archived')"
    )
    op.execute(
        "CREATE TYPE keyword_match_type AS ENUM ('exact', 'contains', 'phrase')"
    )

    op.create_table(
        "users",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )

    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_organizations_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
    )
    op.create_index(
        "ix_organizations_owner_user_id",
        "organizations",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_organizations_created_at",
        "organizations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "uq_organizations_slug_lower",
        "organizations",
        [sa.text("lower(slug)")],
        unique=True,
    )

    op.create_table(
        "organization_members",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "owner",
                "admin",
                "member",
                name="organization_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_members_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_organization_members_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_members"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_members_org_user",
        ),
    )
    op.create_index(
        "ix_organization_members_organization_id",
        "organization_members",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_organization_members_user_id",
        "organization_members",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_organization_members_created_at",
        "organization_members",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "social_accounts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "platform",
            postgresql.ENUM(
                "instagram",
                "facebook",
                name="social_platform",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("platform_account_id", sa.String(length=255), nullable=False),
        sa.Column("account_name", sa.String(length=200), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_connected",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_social_accounts_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_social_accounts"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_social_accounts_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "platform",
            "platform_account_id",
            name="uq_social_accounts_org_platform_account",
        ),
    )
    op.create_index(
        "ix_social_accounts_organization_id",
        "social_accounts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_social_accounts_platform_account_id",
        "social_accounts",
        ["platform_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_social_accounts_is_connected",
        "social_accounts",
        ["is_connected"],
        unique=False,
    )
    op.create_index(
        "ix_social_accounts_created_at",
        "social_accounts",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "automations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("social_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("content_url", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "active",
                "paused",
                "archived",
                name="automation_status",
                create_type=False,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "public_reply_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("public_reply_text", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automations_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_automations_org_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automations"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_automations_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            "social_account_id",
            name="uq_automations_org_id_account",
        ),
    )
    op.create_index(
        "ix_automations_organization_id",
        "automations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_automations_social_account_id",
        "automations",
        ["social_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_automations_status",
        "automations",
        ["status"],
        unique=False,
    )
    op.create_index("ix_automations_created_at", "automations", ["created_at"], unique=False)

    op.create_table(
        "automation_keywords",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column(
            "match_type",
            postgresql.ENUM(
                "exact",
                "contains",
                "phrase",
                name="keyword_match_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automation_keywords_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "automation_id"],
            ["automations.organization_id", "automations.id"],
            name="fk_automation_keywords_org_automation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_keywords"),
    )
    op.create_index(
        "ix_automation_keywords_organization_id",
        "automation_keywords",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_automation_keywords_automation_id",
        "automation_keywords",
        ["automation_id"],
        unique=False,
    )
    op.create_index(
        "ix_automation_keywords_is_active",
        "automation_keywords",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_automation_keywords_created_at",
        "automation_keywords",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "uq_automation_keywords_org_automation_keyword_lower",
        "automation_keywords",
        ["organization_id", "automation_id", sa.text("lower(keyword)")],
        unique=True,
    )

    op.create_table(
        "messages",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("social_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_platform_id", sa.String(length=255), nullable=False),
        sa.Column("message_type", sa.String(length=40), nullable=False),
        sa.Column("message_content", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(length=40), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_messages_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_messages_org_social_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "automation_id", "social_account_id"],
            [
                "automations.organization_id",
                "automations.id",
                "automations.social_account_id",
            ],
            name="fk_messages_org_automation_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_messages_org_id",
        ),
    )
    op.create_index(
        "ix_messages_organization_id",
        "messages",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_messages_automation_id",
        "messages",
        ["automation_id"],
        unique=False,
    )
    op.create_index(
        "ix_messages_social_account_id",
        "messages",
        ["social_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_messages_recipient_platform_id",
        "messages",
        ["recipient_platform_id"],
        unique=False,
    )
    op.create_index(
        "ix_messages_delivery_status",
        "messages",
        ["delivery_status"],
        unique=False,
    )
    op.create_index("ix_messages_created_at", "messages", ["created_at"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_name", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("billing_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount >= 0", name="ck_subscriptions_amount_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_subscriptions_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
    )
    op.create_index(
        "ix_subscriptions_organization_id",
        "subscriptions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscriptions_status",
        "subscriptions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_subscriptions_created_at",
        "subscriptions",
        ["created_at"],
        unique=False,
    )

    for table in (
        "organizations",
        "organization_members",
        "social_accounts",
        "automations",
        "automation_keywords",
        "messages",
        "subscriptions",
    ):
        tenant_column = "id" if table == "organizations" else "organization_id"
        predicate = (
            f"{tenant_column} = "
            "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in (
        "subscriptions",
        "messages",
        "automation_keywords",
        "automations",
        "social_accounts",
        "organization_members",
        "organizations",
        "users",
    ):
        op.drop_table(table)

    op.execute("DROP TYPE keyword_match_type")
    op.execute("DROP TYPE automation_status")
    op.execute("DROP TYPE social_platform")
    op.execute("DROP TYPE organization_role")
