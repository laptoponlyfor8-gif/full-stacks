from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    mobile_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    email_verified: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )
    auth_version: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )

    owned_organizations: Mapped[list[Organization]] = relationship(
        back_populates="owner",
        passive_deletes="all",
    )
    memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="user",
        passive_deletes="all",
    )
