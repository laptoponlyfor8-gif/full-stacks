from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class MessageDeliveryAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "message_delivery_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_message_delivery_attempts_org_message",
            ondelete="RESTRICT",
        ),
        Index("ix_message_delivery_attempts_message_created", "message_id", "created_at"),
        Index("ix_message_delivery_attempts_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
