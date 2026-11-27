from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AutomationStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, enum_values

if TYPE_CHECKING:
    from app.models.automation_keyword import AutomationKeyword
    from app.models.message import Message
    from app.models.organization import Organization
    from app.models.social_account import SocialAccount


class Automation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_automations_org_id"),
        Index("ix_automations_platform_content", "organization_id", "social_account_id", "platform_content_id"),
        UniqueConstraint(
            "organization_id",
            "id",
            "social_account_id",
            name="uq_automations_org_id_account",
        ),
        ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_automations_org_account",
            ondelete="RESTRICT",
        ),
        Index("ix_automations_status", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    content_url: Mapped[str] = mapped_column(Text, nullable=False)
    platform_content_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="comment", server_default="comment")
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(
            AutomationStatus,
            name="automation_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
        server_default=AutomationStatus.DRAFT.value,
    )
    public_reply_enabled: Mapped[bool] = mapped_column(
        nullable=False,
        server_default="false",
    )
    public_reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="automations")
    social_account: Mapped[SocialAccount] = relationship(
        back_populates="automations",
        primaryjoin=(
            "and_(foreign(Automation.social_account_id) == SocialAccount.id, "
            "Automation.organization_id == SocialAccount.organization_id)"
        ),
    )
    keywords: Mapped[list[AutomationKeyword]] = relationship(
        back_populates="automation",
        primaryjoin=(
            "and_(Automation.id == foreign(AutomationKeyword.automation_id), "
            "Automation.organization_id == AutomationKeyword.organization_id)"
        ),
        passive_deletes="all",
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="automation",
        primaryjoin=(
            "and_(Automation.id == foreign(Message.automation_id), "
            "Automation.organization_id == Message.organization_id, "
            "Automation.social_account_id == Message.social_account_id)"
        ),
        passive_deletes="all",
    )
