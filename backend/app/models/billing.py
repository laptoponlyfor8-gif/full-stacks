from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


OPEN_SUBSCRIPTION_STATUSES = (
    "creating",
    "creation_unknown",
    "created",
    "authenticated",
    "active",
    "pending",
    "halted",
    "paused",
)


class BillingPlan(TimestampMixin, Base):
    __tablename__ = "billing_plans"
    __table_args__ = (
        CheckConstraint("amount_subunits = 29900", name="monthly_amount"),
        CheckConstraint("currency = 'INR'", name="currency_inr"),
    )

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    razorpay_plan_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provisioning_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="ready",
    )


class BillingCustomer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_customers"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_billing_customers_organization"),
        UniqueConstraint("razorpay_customer_id", name="uq_billing_customers_razorpay_id"),
        Index("ix_billing_customers_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    razorpay_customer_id: Mapped[str] = mapped_column(String(100), nullable=False)

    organization: Mapped[Organization] = relationship()


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("razorpay_payment_id", name="uq_payments_razorpay_payment_id"),
        ForeignKeyConstraint(
            ["organization_id", "subscription_id"],
            ["subscriptions.organization_id", "subscriptions.id"],
            name="fk_payments_org_subscription",
            ondelete="RESTRICT",
        ),
        Index("ix_payments_org_created", "organization_id", "created_at"),
        Index("ix_payments_org_subscription", "organization_id", "subscription_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    razorpay_payment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_period_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    billing_period_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class BillingWebhookEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        UniqueConstraint("razorpay_event_id", name="uq_billing_webhook_events_event_id"),
        Index("ix_billing_webhook_events_org_received", "organization_id", "received_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    razorpay_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="processed",
    )


class BillingEventLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "billing_event_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "subscription_id"],
            ["subscriptions.organization_id", "subscriptions.id"],
            name="fk_billing_event_logs_org_subscription",
            ondelete="RESTRICT",
        ),
        Index("ix_billing_event_logs_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
