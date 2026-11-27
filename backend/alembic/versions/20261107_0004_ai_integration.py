"""Add organization-scoped AI conversations, configuration, knowledge and usage."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0004"
down_revision: str | None = "20261107_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_configurations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_provider_configurations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", name="pk_ai_provider_configurations"),
    )

    op.create_table(
        "ai_conversations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_conversations_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_conversations"),
        sa.UniqueConstraint("organization_id", "id", name="uq_ai_conversations_org_id"),
    )
    op.create_index(
        "ix_ai_conversations_organization_id",
        "ai_conversations",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_conversations_org_updated",
        "ai_conversations",
        ["organization_id", "updated_at"],
    )
    op.create_index("ix_ai_conversations_created_at", "ai_conversations", ["created_at"])

    op.create_table(
        "ai_messages",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["ai_conversations.organization_id", "ai_conversations.id"],
            name="fk_ai_messages_org_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_messages"),
    )
    op.create_index("ix_ai_messages_organization_id", "ai_messages", ["organization_id"])
    op.create_index(
        "ix_ai_messages_org_conversation_created",
        "ai_messages",
        ["organization_id", "conversation_id", "created_at"],
    )
    op.create_index("ix_ai_messages_created_at", "ai_messages", ["created_at"])

    op.create_table(
        "business_knowledge",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_name", sa.String(length=160), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("products_services", sa.Text(), server_default="", nullable=False),
        sa.Column("faqs", sa.Text(), server_default="", nullable=False),
        sa.Column("website_information", sa.Text(), server_default="", nullable=False),
        sa.Column("custom_instructions", sa.Text(), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_business_knowledge_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", name="pk_business_knowledge"),
    )

    op.create_table(
        "ai_usage_records",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("request_status", sa.String(length=20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_usage_records_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage_records"),
    )
    op.create_index("ix_ai_usage_records_organization_id", "ai_usage_records", ["organization_id"])
    op.create_index(
        "ix_ai_usage_org_created",
        "ai_usage_records",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_org_provider_model",
        "ai_usage_records",
        ["organization_id", "provider", "model"],
    )
    op.create_index("ix_ai_usage_records_created_at", "ai_usage_records", ["created_at"])

    for table in (
        "ai_provider_configurations",
        "ai_conversations",
        "ai_messages",
        "business_knowledge",
        "ai_usage_records",
    ):
        predicate = (
            "organization_id = "
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
        "ai_usage_records",
        "business_knowledge",
        "ai_messages",
        "ai_conversations",
        "ai_provider_configurations",
    ):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
