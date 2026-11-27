from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class AutomationExecution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "automation_id"],
            ["automations.organization_id", "automations.id"],
            name="fk_automation_executions_org_automation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "webhook_event_id"],
            ["webhook_events.organization_id", "webhook_events.id"],
            name="fk_automation_executions_org_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "matched_keyword_id"],
            ["automation_keywords.organization_id", "automation_keywords.id"],
            name="fk_automation_executions_org_keyword",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "webhook_event_id",
            "automation_id",
            name="uq_automation_executions_event_automation",
        ),
        Index("ix_automation_executions_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    webhook_event_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    matched_keyword_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
