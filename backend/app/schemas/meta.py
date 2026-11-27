from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.enums import SocialPlatform


class OAuthStartResponse(BaseModel):
    authorization_url: str


class SocialAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: SocialPlatform
    platform_account_id: str
    account_name: str
    created_at: datetime
    token_expires_at: datetime | None
    is_connected: bool
    connection_status: Literal["connected", "expired", "disconnected"]


class FacebookPageOption(BaseModel):
    platform_account_id: str
    account_name: str


class FacebookPageSelection(BaseModel):
    platform_account_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    ]


class OAuthCallbackResponse(BaseModel):
    message: str
