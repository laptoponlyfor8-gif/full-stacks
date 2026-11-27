from functools import lru_cache
import base64
import binascii
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "DM Karo API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    database_url: SecretStr = SecretStr("postgresql+asyncpg://localhost:5432/dm_karo")
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    health_check_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_issuer: str = "dm-karo-api"
    jwt_audience: str = "dm-karo-web"
    access_token_minutes: int = Field(default=10, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    password_reset_token_minutes: int = Field(default=30, ge=5, le=120)
    email_verification_token_hours: int = Field(default=24, ge=1, le=168)
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["strict", "lax", "none"] = "strict"
    auth_cookie_domain: str | None = None
    auth_rate_limit_window_seconds: int = Field(default=900, ge=1, le=86400)
    auth_login_rate_limit: int = Field(default=10, ge=1, le=100)
    auth_sensitive_rate_limit: int = Field(default=5, ge=1, le=100)
    public_app_url: str = "http://127.0.0.1:5173"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    smtp_starttls: bool = True
    meta_app_id: str | None = None
    meta_app_secret: SecretStr | None = None
    meta_redirect_uri: str | None = None
    meta_webhook_verify_token: SecretStr | None = None
    meta_graph_api_version: str = "v27.0"
    meta_facebook_login_config_id: str | None = None
    meta_token_encryption_key: SecretStr = SecretStr("")
    webhook_rate_limit_per_minute: int = Field(default=600, ge=10, le=10000)
    automation_worker_max_attempts: int = Field(default=5, ge=1, le=20)
    automation_worker_block_ms: int = Field(default=5000, ge=100, le=30000)
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    razorpay_key_id: str | None = None
    razorpay_key_secret: SecretStr | None = None
    razorpay_webhook_secret: SecretStr | None = None
    razorpay_mode: Literal["test"] = "test"
    billing_grace_period_days: int = Field(default=7, ge=0, le=30)
    ai_openai_model: str = "gpt-6-astra"
    ai_gemini_model: str = "gemini-3.8-flash"
    ai_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    ai_requests_per_minute: int = Field(default=20, ge=1, le=1000)
    ai_daily_request_limit: int = Field(default=100, ge=1, le=100000)
    ai_max_input_characters: int = Field(default=12000, ge=1000, le=100000)
    ai_max_output_tokens: int = Field(default=1000, ge=64, le=8192)
    ai_openai_input_cost_per_million: float | None = Field(default=None, ge=0)
    ai_openai_output_cost_per_million: float | None = Field(default=None, ge=0)
    ai_gemini_input_cost_per_million: float | None = Field(default=None, ge=0)
    ai_gemini_output_cost_per_million: float | None = Field(default=None, ge=0)

    @field_validator("database_url")
    @classmethod
    def require_asyncpg_driver(cls, value: SecretStr) -> SecretStr:
        try:
            parsed_url = make_url(value.get_secret_value())
        except (ArgumentError, TypeError, ValueError) as exc:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL.") from exc
        if parsed_url.drivername != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver.")
        if not parsed_url.database:
            raise ValueError("DATABASE_URL must include a database name.")
        return value

    @field_validator("redis_url")
    @classmethod
    def require_redis_url(cls, value: SecretStr) -> SecretStr:
        try:
            parsed_url = urlsplit(value.get_secret_value())
            hostname = parsed_url.hostname
            parsed_url.port
        except ValueError as exc:
            raise ValueError("REDIS_URL must be a valid redis:// or rediss:// URL.") from exc
        if parsed_url.scheme not in {"redis", "rediss"} or not hostname:
            raise ValueError("REDIS_URL must be a valid redis:// or rediss:// URL.")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret and len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes.")
        return value

    @field_validator("smtp_from_email")
    @classmethod
    def validate_smtp_sender(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("SMTP_FROM_EMAIL must not be blank.")
        return value.strip() if value else value

    @field_validator("public_app_url")
    @classmethod
    def validate_public_app_url(cls, value: str) -> str:
        parsed_url = urlsplit(value)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.path not in {"", "/"}
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ValueError("PUBLIC_APP_URL must be an HTTP(S) origin.")
        return value.rstrip("/")

    @field_validator("meta_app_id", "meta_facebook_login_config_id")
    @classmethod
    def normalize_meta_identifiers(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("meta_app_secret", "meta_webhook_verify_token", mode="before")
    @classmethod
    def normalize_meta_secrets(cls, value: str | SecretStr | None) -> str | SecretStr | None:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("meta_graph_api_version")
    @classmethod
    def validate_meta_graph_api_version(cls, value: str) -> str:
        if not re.fullmatch(r"v\d+\.\d+", value):
            raise ValueError("META_GRAPH_API_VERSION must look like v27.0.")
        return value

    @field_validator("meta_redirect_uri")
    @classmethod
    def validate_meta_redirect_uri(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        parsed_url = urlsplit(value)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.path != "/api/v1/meta/oauth/callback"
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ValueError(
                "META_REDIRECT_URI must be the exact /api/v1/meta/oauth/callback URL."
            )
        return value

    @field_validator("meta_token_encryption_key")
    @classmethod
    def validate_meta_encryption_key(cls, value: SecretStr) -> SecretStr:
        encoded = value.get_secret_value()
        if not encoded:
            return value
        try:
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise ValueError(
                "META_TOKEN_ENCRYPTION_KEY must be URL-safe base64 for 32 random bytes."
            ) from exc
        if (
            len(key) != 32
            or base64.urlsafe_b64encode(key).decode("ascii") != encoded
        ):
            raise ValueError(
                "META_TOKEN_ENCRYPTION_KEY must be URL-safe base64 for 32 random bytes."
            )
        return value

    @field_validator("auth_cookie_domain")
    @classmethod
    def normalize_cookie_domain(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("openai_api_key", "gemini_api_key", mode="before")
    @classmethod
    def normalize_ai_secrets(cls, value: str | SecretStr | None) -> str | SecretStr | None:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @field_validator(
        "razorpay_key_secret",
        "razorpay_webhook_secret",
        mode="before",
    )
    @classmethod
    def normalize_razorpay_secrets(
        cls,
        value: str | SecretStr | None,
    ) -> str | SecretStr | None:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("razorpay_key_id")
    @classmethod
    def normalize_razorpay_key_id(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("ai_openai_model", "ai_gemini_model")
    @classmethod
    def validate_ai_model_name(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 120 or not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
            raise ValueError("AI model names must contain only letters, numbers, '.', '_', ':' or '-'.")
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            try:
                parsed_origin = urlsplit(origin)
                parsed_origin.port
            except ValueError as exc:
                raise ValueError("CORS_ALLOWED_ORIGINS contains an invalid origin.") from exc
            if (
                origin == "*"
                or parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.username is not None
                or parsed_origin.password is not None
                or parsed_origin.hostname is None
            ):
                raise ValueError("CORS_ALLOWED_ORIGINS must contain HTTP(S) origins without paths.")
        return origins

    @model_validator(mode="after")
    def reject_local_services_in_deployed_environments(self) -> "Settings":
        if self.app_env in {"staging", "production"}:
            database_host = make_url(self.database_url.get_secret_value()).host
            redis_host = urlsplit(self.redis_url.get_secret_value()).hostname
            local_hosts = {"localhost", "127.0.0.1", "::1"}
            if (
                not database_host
                or not redis_host
                or database_host.lower() in local_hosts
                or redis_host.lower() in local_hosts
            ):
                raise ValueError("Staging and production service URLs must not point to localhost.")
            if any(urlsplit(origin).hostname in local_hosts for origin in self.cors_allowed_origins):
                raise ValueError("Staging and production CORS origins must not point to localhost.")
            if len(self.jwt_secret_key.get_secret_value().encode("utf-8")) < 32:
                raise ValueError("JWT_SECRET_KEY must be configured with at least 32 bytes.")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true outside development.")
            if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
                raise ValueError("SameSite=None requires secure authentication cookies.")
        if self.smtp_username and not self.smtp_password:
            raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is configured.")
        if self.smtp_password and not self.smtp_username:
            raise ValueError("SMTP_USERNAME is required when SMTP_PASSWORD is configured.")
        if bool(self.smtp_host) != bool(self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL must be configured together.")
        if bool(self.razorpay_key_id) != bool(self.razorpay_key_secret):
            raise ValueError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be configured together."
            )
        if self.razorpay_key_id and not self.razorpay_key_id.startswith("rzp_test_"):
            raise ValueError("DM Karo billing accepts Razorpay Test Mode keys only.")
        meta_configured = any(
            (
                self.meta_app_id,
                self.meta_app_secret,
                self.meta_redirect_uri,
                self.meta_token_encryption_key.get_secret_value(),
            )
        )
        if meta_configured and not all(
            (
                self.meta_app_id,
                self.meta_app_secret,
                self.meta_redirect_uri,
                self.meta_token_encryption_key.get_secret_value(),
            )
        ):
            raise ValueError(
                "META_APP_ID, META_APP_SECRET, META_REDIRECT_URI and "
                "META_TOKEN_ENCRYPTION_KEY must be configured together."
            )
        if (
            self.meta_redirect_uri
            and self.app_env in {"staging", "production"}
            and urlsplit(self.meta_redirect_uri).scheme != "https"
        ):
            raise ValueError("META_REDIRECT_URI must use HTTPS outside development.")
        if (
            self.app_env in {"staging", "production"}
            and meta_configured
            and self.meta_webhook_verify_token is None
        ):
            raise ValueError("META_WEBHOOK_VERIFY_TOKEN is required when Meta is configured.")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
