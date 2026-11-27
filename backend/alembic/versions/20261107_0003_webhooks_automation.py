"""Add verified webhook intake and tenant-isolated automation processing."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0003"
down_revision: str | None = "20261107_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automations",
        sa.Column("platform_content_id", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "automations",
        sa.Column("trigger_type", sa.String(length=20), nullable=False, server_default="comment"),
    )
    op.add_column("automations", sa.Column("private_reply_text", sa.Text(), nullable=True))
    op.create_index(
        "ix_automations_platform_content",
        "automations",
        ["organization_id", "social_account_id", "platform_content_id"],
    )
    op.create_unique_constraint(
        "uq_automation_keywords_org_id", "automation_keywords", ["organization_id", "id"]
    )

    op.add_column("messages", sa.Column("external_message_id", sa.String(length=255), nullable=True))
    op.add_column("messages", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_messages_idempotency_key", "messages", ["idempotency_key"])

    op.create_table(
        "meta_webhook_account_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("social_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("platform_account_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_meta_webhook_routes_org_social_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meta_webhook_account_routes"),
        sa.UniqueConstraint(
            "platform",
            "platform_account_id",
            "organization_id",
            name="uq_meta_webhook_routes_account_tenant",
        ),
    )
    op.create_index(
        "ix_meta_webhook_routes_platform_account",
        "meta_webhook_account_routes",
        ["platform", "platform_account_id"],
    )
    op.execute(
        """
        INSERT INTO meta_webhook_account_routes
            (id, organization_id, social_account_id, platform, platform_account_id)
        SELECT gen_random_uuid(), organization_id, id, platform::text, platform_account_id
        FROM social_accounts
        """
    )

    op.create_table(
        "webhook_events",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("social_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processing_status", sa.String(length=20), server_default="received", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_category", sa.String(length=60), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_webhook_events_org_social_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_events"),
        sa.UniqueConstraint("idempotency_key", name="uq_webhook_events_idempotency_key"),
        sa.UniqueConstraint("organization_id", "id", name="uq_webhook_events_org_id"),
    )
    op.create_index("ix_webhook_events_organization_id", "webhook_events", ["organization_id"])
    op.create_index("ix_webhook_events_social_account_id", "webhook_events", ["social_account_id"])
    op.create_index("ix_webhook_events_status_available", "webhook_events", ["processing_status", "available_at"])
    op.create_index("ix_webhook_events_org_created", "webhook_events", ["organization_id", "created_at"])

    op.create_table(
        "automation_executions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("matched_keyword_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_category", sa.String(length=60), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "automation_id"],
            ["automations.organization_id", "automations.id"],
            name="fk_automation_executions_org_automation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "webhook_event_id"],
            ["webhook_events.organization_id", "webhook_events.id"],
            name="fk_automation_executions_org_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "matched_keyword_id"],
            ["automation_keywords.organization_id", "automation_keywords.id"],
            name="fk_automation_executions_org_keyword",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_executions"),
        sa.UniqueConstraint(
            "webhook_event_id", "automation_id", name="uq_automation_executions_event_automation"
        ),
    )
    op.create_index("ix_automation_executions_organization_id", "automation_executions", ["organization_id"])
    op.create_index("ix_automation_executions_webhook_event_id", "automation_executions", ["webhook_event_id"])
    op.create_index("ix_automation_executions_automation_id", "automation_executions", ["automation_id"])
    op.create_index("ix_automation_executions_org_status", "automation_executions", ["organization_id", "status"])
    op.create_index("ix_automation_executions_created_at", "automation_executions", ["created_at"])

    op.create_table(
        "message_delivery_attempts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_category", sa.String(length=60), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_message_delivery_attempts_org_message",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_delivery_attempts"),
    )
    op.create_index("ix_message_delivery_attempts_message_id", "message_delivery_attempts", ["message_id"])
    op.create_index(
        "ix_message_delivery_attempts_message_created",
        "message_delivery_attempts",
        ["message_id", "created_at"],
    )
    op.create_index(
        "ix_message_delivery_attempts_organization_id",
        "message_delivery_attempts",
        ["organization_id"],
    )

    for table in ("webhook_events", "automation_executions", "message_delivery_attempts"):
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
    for table in ("message_delivery_attempts", "automation_executions", "webhook_events"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
    op.drop_index("ix_meta_webhook_routes_platform_account", table_name="meta_webhook_account_routes")
    op.drop_table("meta_webhook_account_routes")
    op.drop_constraint("uq_messages_idempotency_key", "messages", type_="unique")
    op.drop_column("messages", "idempotency_key")
    op.drop_column("messages", "external_message_id")
    op.drop_constraint("uq_automation_keywords_org_id", "automation_keywords", type_="unique")
    op.drop_index("ix_automations_platform_content", table_name="automations")
    op.drop_column("automations", "private_reply_text")
    op.drop_column("automations", "trigger_type")
    op.drop_column("automations", "platform_content_id")
