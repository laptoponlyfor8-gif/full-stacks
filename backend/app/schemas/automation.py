from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from typing import Annotated

from app.models.enums import AutomationStatus, KeywordMatchType, SocialPlatform

AutomationName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
ReplyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class KeywordInput(BaseModel):
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    match_type: KeywordMatchType = KeywordMatchType.CONTAINS


class AutomationCreate(BaseModel):
    social_account_id: UUID
    name: AutomationName
    platform: SocialPlatform
    trigger_type: Literal["comment", "direct_message"] = "comment"
    content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] = "Post"
    content_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2048)] = ""
    keywords: list[KeywordInput] = Field(default_factory=list, max_length=50)
    private_reply_text: ReplyText | None = None
    public_reply_enabled: bool = False
    public_reply_text: ReplyText | None = None

    @field_validator("content_url")
    @classmethod
    def validate_content_url(cls, value: str, info):
        if info.data.get("trigger_type") == "direct_message":
            return value
        if not value.startswith("https://"):
            raise ValueError("A direct HTTPS permalink is required for comment automations.")
        return value

    @model_validator(mode="after")
    def validate_reply_configuration(self):
        if self.public_reply_enabled and not self.public_reply_text:
            raise ValueError("Public reply text is required when public replies are enabled.")
        return self


class AutomationUpdate(BaseModel):
    name: AutomationName | None = None
    social_account_id: UUID | None = None
    platform: SocialPlatform | None = None
    content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    content_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2048)] | None = None
    keywords: list[KeywordInput] | None = Field(default=None, max_length=50)
    private_reply_text: ReplyText | None = None
    public_reply_enabled: bool | None = None
    public_reply_text: ReplyText | None = None
    status: AutomationStatus | None = None


class AutomationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    social_account_id: UUID
    platform: SocialPlatform
    account_name: str
    name: str
    trigger_type: str
    content_type: str
    content_url: str
    status: AutomationStatus
    keywords: list[KeywordInput]
    private_reply_text: str | None
    public_reply_enabled: bool
    public_reply_text: str | None
    created_at: datetime
    updated_at: datetime
    executions: int
    sent_messages: int
    failed_messages: int


class AutomationExecutionResponse(BaseModel):
    id: UUID
    status: str
    error_category: str | None
    started_at: datetime
    finished_at: datetime | None
