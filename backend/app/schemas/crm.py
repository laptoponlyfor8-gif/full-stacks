from datetime import datetime
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing import Annotated

from app.models.enums import LeadStatus, SocialPlatform

ContactName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
CustomerId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ContactCreate(BaseModel):
    social_account_id: UUID
    platform_customer_id: CustomerId
    display_name: ContactName = ""
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom_fields")
    @classmethod
    def validate_custom_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 50 or any(not key.strip() or len(key) > 80 for key in value):
            raise ValueError("Custom fields must have at most 50 named entries.")
        if len(json.dumps(value, ensure_ascii=True)) > 10_000:
            raise ValueError("Custom fields are too large.")
        return value


class ContactUpdate(BaseModel):
    display_name: ContactName | None = None
    custom_fields: dict[str, Any] | None = None

    @field_validator("custom_fields")
    @classmethod
    def validate_custom_fields(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        if len(value) > 50 or any(not key.strip() or len(key) > 80 for key in value):
            raise ValueError("Custom fields must have at most 50 named entries.")
        if len(json.dumps(value, ensure_ascii=True)) > 10_000:
            raise ValueError("Custom fields are too large.")
        return value


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    social_account_id: UUID
    platform: SocialPlatform
    platform_customer_id: str
    display_name: str
    lead_status: LeadStatus
    custom_fields: dict[str, Any]
    first_contact_at: datetime | None
    last_interaction_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)


class ContactPage(BaseModel):
    items: list[ContactResponse]
    total: int
    offset: int
    limit: int


class ContactNoteCreate(BaseModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class ContactNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_user_id: UUID
    content: str
    created_at: datetime


class ContactTagCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class ContactTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class ContactTagsUpdate(BaseModel):
    tag_ids: list[UUID] = Field(max_length=30)


class LeadStatusUpdate(BaseModel):
    status: LeadStatus


class ConversationSummary(BaseModel):
    contact_id: UUID
    display_name: str
    platform: SocialPlatform
    platform_customer_id: str
    latest_message_preview: str
    latest_message_at: datetime | None
    unread_count: int
    lead_status: LeadStatus


class ConversationPage(BaseModel):
    items: list[ConversationSummary]
    total: int
    offset: int
    limit: int


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_type: str
    message_content: str
    delivery_status: str
    external_message_id: str | None
    created_at: datetime
    platform_created_at: datetime | None
    is_read: bool


class ConversationDetail(BaseModel):
    contact: ContactResponse
    messages: list[MessageResponse]
    total: int
    offset: int
    limit: int


class ManualMessageCreate(BaseModel):
    text: MessageText
    idempotency_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=120)]


class AnalyticsMetric(BaseModel):
    value: int
    available: bool


class AnalyticsResponse(BaseModel):
    date_from: datetime
    date_to: datetime
    coverage_start: datetime | None
    connected_accounts: AnalyticsMetric
    active_automations: AnalyticsMetric
    automation_executions: AnalyticsMetric
    successful_executions: AnalyticsMetric
    failed_executions: AnalyticsMetric
    messages_sent: AnalyticsMetric
    messages_received: AnalyticsMetric
    total_contacts: AnalyticsMetric
    new_leads: AnalyticsMetric
    converted_leads: AnalyticsMetric
    daily_messages: list[dict[str, Any]]
    weekly_messages: list[dict[str, Any]]
    platform_breakdown: list[dict[str, Any]]
    automation_performance: list[dict[str, Any]]
