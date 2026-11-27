from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.automation import Automation
    from app.models.organization import Organization
    from app.models.social_account import SocialAccount


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_messages_org_social_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "automation_id", "social_account_id"],
            [
                "automations.organization_id",
                "automations.id",
                "automations.social_account_id",
            ],
            name="fk_messages_org_automation_account",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_messages_org_id"),
        UniqueConstraint("idempotency_key", name="uq_messages_idempotency_key"),
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_messages_org_contact",
            ondelete="RESTRICT",
        ),
        Index("ix_messages_recipient_platform_id", "recipient_platform_id"),
        Index("ix_messages_delivery_status", "delivery_status"),
        Index("ix_messages_org_contact_created", "organization_id", "contact_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    automation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    recipient_platform_id: Mapped[str] = mapped_column(String(255), nullable=False)
    message_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(40), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    platform_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    organization: Mapped[Organization] = relationship(back_populates="messages")
    automation: Mapped[Automation | None] = relationship(
        back_populates="messages",
        primaryjoin=(
            "and_(foreign(Message.automation_id) == Automation.id, "
            "Message.organization_id == Automation.organization_id, "
            "Message.social_account_id == Automation.social_account_id)"
        ),
    )
    social_account: Mapped[SocialAccount] = relationship(
        back_populates="messages",
        primaryjoin=(
            "and_(foreign(Message.social_account_id) == SocialAccount.id, "
            "Message.organization_id == SocialAccount.organization_id)"
        ),
    )
