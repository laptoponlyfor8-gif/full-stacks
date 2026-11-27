from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AIProviderName = Literal["openai", "gemini"]
AIAction = Literal[
    "draft_message",
    "suggest_keywords",
    "public_reply",
    "improve_message",
    "translate",
    "summarize",
    "suggested_reply",
    "classify",
]


class AIChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=12_000)


class AIChatResponse(BaseModel):
    conversation_id: UUID
    answer: str
    provider: AIProviderName
    model: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None


class AIMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    provider: str | None
    model: str | None
    created_at: datetime


class AIConversationResponse(BaseModel):
    id: UUID
    title: str
    updated_at: datetime
    messages: list[AIMessageResponse] = Field(default_factory=list)


class AIProviderStatus(BaseModel):
    provider: AIProviderName
    configured: bool
    model: str


class AISettingsResponse(BaseModel):
    providers: list[AIProviderStatus]
    selected_provider: AIProviderName | None
    selected_model: str | None


class AISettingsUpdate(BaseModel):
    provider: AIProviderName
    model: str = Field(min_length=1, max_length=120)


class AIAssistRequest(BaseModel):
    action: AIAction
    input_text: str = Field(min_length=1, max_length=12_000)
    context: str = Field(default="", max_length=12_000)
    language: str = Field(default="", max_length=80)


class AIAssistResponse(BaseModel):
    result: str
    provider: AIProviderName
    model: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None


class BusinessKnowledgeUpdate(BaseModel):
    business_name: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=4000)
    products_services: str = Field(default="", max_length=8000)
    faqs: str = Field(default="", max_length=8000)
    website_information: str = Field(default="", max_length=8000)
    custom_instructions: str = Field(default="", max_length=4000)


class BusinessKnowledgeResponse(BusinessKnowledgeUpdate):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime | None


class AIUsageSummary(BaseModel):
    since: datetime
    until: datetime
    request_count: int
    successful_count: int
    failed_count: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    daily_request_limit: int
