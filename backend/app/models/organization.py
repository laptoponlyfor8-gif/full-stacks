from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.automation import Automation
    from app.models.message import Message
    from app.models.organization_member import OrganizationMember
    from app.models.social_account import SocialAccount
    from app.models.subscription import Subscription
    from app.models.user import User


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("uq_organizations_slug_lower", text("lower(slug)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    owner: Mapped[User] = relationship(back_populates="owned_organizations")
    memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization",
        passive_deletes="all",
    )
    social_accounts: Mapped[list[SocialAccount]] = relationship(
        back_populates="organization",
        passive_deletes="all",
    )
    automations: Mapped[list[Automation]] = relationship(
        back_populates="organization",
        passive_deletes="all",
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="organization",
        passive_deletes="all",
    )
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="organization",
        passive_deletes="all",
    )
