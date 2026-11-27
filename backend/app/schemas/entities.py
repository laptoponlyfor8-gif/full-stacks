from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from app.models.enums import (
    AutomationStatus,
    KeywordMatchType,
    OrganizationRole,
    SocialPlatform,
)

NonEmptyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
OrganizationSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]


class OrganizationCreate(BaseModel):
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ]
    slug: OrganizationSlug
    owner_user_id: UUID


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: NonEmptyName
    email: EmailStr
    is_active: bool
    email_verified: bool


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: NonEmptyName
    slug: OrganizationSlug
    owner_user_id: UUID
    is_active: bool


class OrganizationMemberCreate(BaseModel):
    organization_id: UUID
    user_id: UUID
    role: OrganizationRole


class OrganizationMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: OrganizationRole


class SocialAccountCreate(BaseModel):
    organization_id: UUID
    platform: SocialPlatform
    platform_account_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    ]
    account_name: NonEmptyName


class SocialAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    platform: SocialPlatform
    platform_account_id: str
    account_name: NonEmptyName
    token_expires_at: datetime | None
    is_connected: bool


class AutomationCreate(BaseModel):
    organization_id: UUID
    social_account_id: UUID
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ]
    content_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    content_type: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    ]
    status: AutomationStatus = AutomationStatus.DRAFT
    public_reply_enabled: bool = False
    public_reply_text: str | None = None


class AutomationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    social_account_id: UUID
    name: NonEmptyName
    content_url: str
    content_type: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    ]
    status: AutomationStatus
    public_reply_enabled: bool
    public_reply_text: str | None


class AutomationKeywordCreate(BaseModel):
    organization_id: UUID
    automation_id: UUID
    keyword: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    match_type: KeywordMatchType
    is_active: bool = True


class AutomationKeywordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    automation_id: UUID
    keyword: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    match_type: KeywordMatchType
    is_active: bool


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    automation_id: UUID | None
    social_account_id: UUID
    recipient_platform_id: str
    message_type: str
    message_content: str
    delivery_status: str


class SubscriptionCreate(BaseModel):
    organization_id: UUID
    plan_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    amount: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    status: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    ]


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    plan_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    amount: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    status: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    ]
