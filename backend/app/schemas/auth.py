from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Password = Annotated[
    str,
    StringConstraints(min_length=8, max_length=128),
]
DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class RegisterRequest(BaseModel):
    name: DisplayName
    business_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ]
    email: EmailStr
    mobile_number: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=7, max_length=32),
    ] = None
    password: Password
    confirm_password: Password

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password confirmation does not match.")
        if len(self.password.encode("utf-8")) > 1024:
            raise ValueError("Password is too long.")
        if self.mobile_number and not all(
            character.isdigit() or character in "+()- ."
            for character in self.mobile_number
        ):
            raise ValueError("Enter a valid mobile number.")
        return self

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(character for character in value if character.isdigit())
        if not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid mobile number.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    remember_me: bool = False


class EmailRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    password: Password
    confirm_password: Password

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password confirmation does not match.")
        if len(self.password.encode("utf-8")) > 1024:
            raise ValueError("Password is too long.")
        return self


class VerifyEmailRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class OrganizationSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str


class AuthenticatedUser(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    email_verified: bool
    organization: OrganizationSummary


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class RegistrationResponse(BaseModel):
    id: UUID
    email: EmailStr
    email_verification_sent: bool
    message: str


class GenericMessage(BaseModel):
    message: str


class MembershipResponse(BaseModel):
    organization_id: UUID
    role: str


class AuthSessionResponse(BaseModel):
    user: AuthenticatedUser
    organizations: list[OrganizationSummary]
    authenticated_at: datetime = Field(default_factory=datetime.now)
