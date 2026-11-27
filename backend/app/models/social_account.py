from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SocialPlatform
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, enum_values

if TYPE_CHECKING:
    from app.models.automation import Automation
    from app.models.message import Message
    from app.models.organization import Organization


class SocialAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_social_accounts_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            "platform",
            "platform_account_id",
            name="uq_social_accounts_org_platform_account",
        ),
        Index("ix_social_accounts_platform_account_id", "platform_account_id"),
        Index("ix_social_accounts_is_connected", "is_connected"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(
            SocialPlatform,
            name="social_platform",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    platform_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_connected: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    organization: Mapped[Organization] = relationship(back_populates="social_accounts")
    automations: Mapped[list[Automation]] = relationship(
        back_populates="social_account",
        primaryjoin=(
            "and_(SocialAccount.id == foreign(Automation.social_account_id), "
            "SocialAccount.organization_id == Automation.organization_id)"
        ),
        passive_deletes="all",
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="social_account",
        primaryjoin=(
            "and_(SocialAccount.id == foreign(Message.social_account_id), "
            "SocialAccount.organization_id == Message.organization_id)"
        ),
        passive_deletes="all",
    )
