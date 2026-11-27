from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class WebhookEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_webhook_events_org_social_account",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("idempotency_key", name="uq_webhook_events_idempotency_key"),
        UniqueConstraint("organization_id", "id", name="uq_webhook_events_org_id"),
        Index("ix_webhook_events_status_available", "processing_status", "available_at"),
        Index("ix_webhook_events_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="received", server_default="received"
    )
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    error_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MetaWebhookAccountRoute(Base):
    """Non-PII routing index used to map signed provider IDs to tenant-owned rows."""

    __tablename__ = "meta_webhook_account_routes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_meta_webhook_routes_org_social_account",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "platform",
            "platform_account_id",
            "organization_id",
            name="uq_meta_webhook_routes_account_tenant",
        ),
        Index("ix_meta_webhook_routes_platform_account", "platform", "platform_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
