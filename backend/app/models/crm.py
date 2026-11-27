from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Contact(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_contacts_org_id"),
        UniqueConstraint(
            "organization_id",
            "social_account_id",
            "platform_customer_id",
            name="uq_contacts_org_account_platform_customer",
        ),
        ForeignKeyConstraint(
            ["organization_id", "social_account_id"],
            ["social_accounts.organization_id", "social_accounts.id"],
            name="fk_contacts_org_social_account",
            ondelete="RESTRICT",
        ),
        Index("ix_contacts_org_status_updated", "organization_id", "lead_status", "updated_at"),
        Index("ix_contacts_org_last_interaction", "organization_id", "last_interaction_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    platform_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    lead_status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", server_default="new")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    first_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ContactNote(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "contact_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_contact_notes_org_contact",
            ondelete="CASCADE",
        ),
        Index("ix_contact_notes_org_contact_created", "organization_id", "contact_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)


class ContactTag(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "contact_tags"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_contact_tags_org_id"),
        UniqueConstraint("organization_id", "name", name="uq_contact_tags_org_name"),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_contact_tags_org",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)


class ContactTagAssignment(Base):
    __tablename__ = "contact_tag_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_contact_tag_assignments_org_contact",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "tag_id"],
            ["contact_tags.organization_id", "contact_tags.id"],
            name="fk_contact_tag_assignments_org_tag",
            ondelete="CASCADE",
        ),
        Index("ix_contact_tag_assignments_org_tag", "organization_id", "tag_id"),
        Index("ix_contact_tag_assignments_created_at", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class LeadActivity(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "lead_activities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_lead_activities_org_contact",
            ondelete="CASCADE",
        ),
        Index("ix_lead_activities_org_contact_created", "organization_id", "contact_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
