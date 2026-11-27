"""Add Test Mode Razorpay subscriptions, payments and webhook records."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0006"
down_revision: str | None = "20261107_0005"
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
    op.add_column(
        "subscriptions",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("subscriptions", sa.Column("razorpay_customer_id", sa.String(100), nullable=True))
    op.add_column("subscriptions", sa.Column("razorpay_subscription_id", sa.String(100), nullable=True))
    op.add_column("subscriptions", sa.Column("razorpay_plan_id", sa.String(100), nullable=True))
    op.add_column("subscriptions", sa.Column("next_billing_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("grace_period_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "subscriptions",
        sa.Column("cancel_at_cycle_end", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("subscriptions", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("last_provider_event_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        "uq_subscriptions_org_id",
        "subscriptions",
        ["organization_id", "id"],
    )
    op.create_unique_constraint(
        "uq_subscriptions_razorpay_subscription_id",
        "subscriptions",
        ["razorpay_subscription_id"],
    )
    op.create_index(
        "uq_subscriptions_org_open",
        "subscriptions",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('creating','creation_unknown') OR "
            "(razorpay_subscription_id IS NOT NULL AND status IN "
            "('created','authenticated','active','pending','halted','paused'))"
        ),
        sqlite_where=sa.text(
            "status IN ('creating','creation_unknown') OR "
            "(razorpay_subscription_id IS NOT NULL AND status IN "
            "('created','authenticated','active','pending','halted','paused'))"
        ),
    )

    op.create_table(
        "billing_plans",
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("razorpay_plan_id", sa.String(length=100), nullable=True),
        sa.Column("plan_name", sa.String(length=100), nullable=False),
        sa.Column("amount_subunits", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provisioning_status", sa.String(length=30), server_default="ready", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_billing_plans"),
        sa.UniqueConstraint("razorpay_plan_id", name="uq_billing_plans_razorpay_plan_id"),
        sa.CheckConstraint("amount_subunits = 29900", name="ck_billing_plans_monthly_amount"),
        sa.CheckConstraint("currency = 'INR'", name="ck_billing_plans_currency_inr"),
    )
    op.create_table(
        "billing_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("razorpay_customer_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_billing_customers_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_billing_customers"),
        sa.UniqueConstraint("organization_id", name="uq_billing_customers_organization"),
        sa.UniqueConstraint("razorpay_customer_id", name="uq_billing_customers_razorpay_id"),
    )
    op.create_index("ix_billing_customers_organization_id", "billing_customers", ["organization_id"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provider_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_period_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_period_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_payments_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "subscription_id"],
            ["subscriptions.organization_id", "subscriptions.id"],
            name="fk_payments_org_subscription",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("razorpay_payment_id", name="uq_payments_razorpay_payment_id"),
    )
    op.create_index("ix_payments_org_created", "payments", ["organization_id", "created_at"])
    op.create_index("ix_payments_org_subscription", "payments", ["organization_id", "subscription_id"])

    op.create_table(
        "billing_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("razorpay_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("razorpay_subscription_id", sa.String(length=100), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=30), server_default="processed", nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_billing_webhook_events_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_billing_webhook_events"),
        sa.UniqueConstraint("razorpay_event_id", name="uq_billing_webhook_events_event_id"),
    )
    op.create_index(
        "ix_billing_webhook_events_org_received",
        "billing_webhook_events",
        ["organization_id", "received_at"],
    )

    op.create_table(
        "billing_event_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("previous_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_billing_event_logs_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "subscription_id"],
            ["subscriptions.organization_id", "subscriptions.id"],
            name="fk_billing_event_logs_org_subscription",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_billing_event_logs"),
    )
    op.create_index(
        "ix_billing_event_logs_org_created",
        "billing_event_logs",
        ["organization_id", "created_at"],
    )
    _enable_tenant_isolation(
        ("billing_customers", "payments", "billing_webhook_events", "billing_event_logs")
    )


def downgrade() -> None:
    for table in ("billing_event_logs", "billing_webhook_events", "payments", "billing_customers"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index("ix_billing_event_logs_org_created", table_name="billing_event_logs")
    op.drop_table("billing_event_logs")
    op.drop_index("ix_billing_webhook_events_org_received", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
    op.drop_index("ix_payments_org_subscription", table_name="payments")
    op.drop_index("ix_payments_org_created", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_billing_customers_organization_id", table_name="billing_customers")
    op.drop_table("billing_customers")
    op.drop_table("billing_plans")
    op.drop_index("uq_subscriptions_org_open", table_name="subscriptions")
    op.drop_constraint(
        "uq_subscriptions_razorpay_subscription_id",
        "subscriptions",
        type_="unique",
    )
    op.drop_constraint("uq_subscriptions_org_id", "subscriptions", type_="unique")
    for column in (
        "last_provider_event_at",
        "cancellation_requested_at",
        "cancel_at_cycle_end",
        "next_billing_at",
        "grace_period_ends_at",
        "razorpay_plan_id",
        "razorpay_subscription_id",
        "razorpay_customer_id",
        "updated_at",
    ):
        op.drop_column("subscriptions", column)
