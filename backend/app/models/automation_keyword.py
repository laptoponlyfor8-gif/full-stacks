from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import KeywordMatchType
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, enum_values

if TYPE_CHECKING:
    from app.models.automation import Automation
    from app.models.organization import Organization


class AutomationKeyword(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "automation_keywords"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_automation_keywords_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "automation_id"],
            ["automations.organization_id", "automations.id"],
            name="fk_automation_keywords_org_automation",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_automation_keywords_org_automation_keyword_lower",
            "organization_id",
            "automation_id",
            text("lower(keyword)"),
            unique=True,
        ),
        Index("ix_automation_keywords_automation_id", "automation_id"),
        Index("ix_automation_keywords_is_active", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    match_type: Mapped[KeywordMatchType] = mapped_column(
        Enum(
            KeywordMatchType,
            name="keyword_match_type",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    organization: Mapped[Organization] = relationship()
    automation: Mapped[Automation] = relationship(
        back_populates="keywords",
        primaryjoin=(
            "and_(foreign(AutomationKeyword.automation_id) == Automation.id, "
            "AutomationKeyword.organization_id == Automation.organization_id)"
        ),
    )
