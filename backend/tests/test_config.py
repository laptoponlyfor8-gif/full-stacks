import base64

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_configuration_accepts_asyncpg_and_redis_urls() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user@localhost:5432/dm_karo",
        redis_url="rediss://cache.example.test:6380/0",
    )
    assert settings.database_url.get_secret_value().startswith("postgresql+asyncpg://")
    assert isinstance(settings.redis_url, SecretStr)
    assert settings.docs_enabled is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql://user@localhost:5432/dm_karo"),
        ("database_url", "postgresql+psycopg://user@localhost:5432/dm_karo"),
        ("database_url", "postgresql+asyncpg://localhost:5432"),
        ("database_url", "not-a-valid-url"),
        ("redis_url", "http://localhost:6379"),
        ("redis_url", "redis://[invalid-ipv6"),
    ],
)
def test_configuration_rejects_unsupported_or_incomplete_service_urls(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize(
    "origins",
    [
        ["*"],
        ["localhost:5173"],
        ["https://example.test/unexpected-path"],
        ["https://user:password@example.test"],
        ["https://example.test:invalid"],
    ],
)
def test_configuration_rejects_unsafe_cors_origins(origins: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_allowed_origins=origins)


def test_production_environment_disables_interactive_api_documentation() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://db.internal:5432/dm_karo",
        redis_url="redis://cache.internal:6379/0",
        cors_allowed_origins=["https://app.example.test"],
        jwt_secret_key="production-test-secret-0123456789-abcdefgh",
        auth_cookie_secure=True,
    )
    assert settings.docs_enabled is False


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_reject_default_local_service_urls(environment: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env=environment)


def test_deployed_environments_reject_database_urls_without_a_host() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg:///dm_karo",
            redis_url="redis://cache.internal:6379/0",
            cors_allowed_origins=["https://app.example.test"],
        )


def test_meta_configuration_requires_a_fixed_callback_and_32_byte_encryption_key() -> None:
    key = base64.urlsafe_b64encode(b"c" * 32).decode()
    settings = Settings(
        _env_file=None,
        meta_app_id="test-app",
        meta_app_secret="test-secret",
        meta_redirect_uri="http://localhost:8000/api/v1/meta/oauth/callback",
        meta_graph_api_version="v27.0",
        meta_token_encryption_key=key,
    )
    assert settings.meta_redirect_uri.endswith("/api/v1/meta/oauth/callback")

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            meta_app_id="test-app",
            meta_app_secret="test-secret",
            meta_redirect_uri="http://localhost:8000/unsafe/callback",
            meta_token_encryption_key=key,
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            meta_app_id="test-app",
            meta_app_secret="test-secret",
            meta_redirect_uri="http://localhost:8000/api/v1/meta/oauth/callback",
            meta_token_encryption_key="not-a-valid-key",
        )


def test_razorpay_configuration_accepts_test_keys_and_rejects_live_or_partial_keys() -> None:
    settings = Settings(
        _env_file=None,
        razorpay_mode="test",
        razorpay_key_id="rzp_test_example",
        razorpay_key_secret="test-secret",
        razorpay_webhook_secret="webhook-secret",
    )
    assert settings.razorpay_key_id == "rzp_test_example"
    assert isinstance(settings.razorpay_key_secret, SecretStr)
    assert settings.billing_grace_period_days == 7

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            razorpay_mode="live",
            razorpay_key_id="rzp_live_example",
            razorpay_key_secret="live-secret",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            razorpay_key_id="rzp_test_example",
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, billing_grace_period_days=31)
