from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import ai as ai_api
from app.core.config import Settings
from app.core.security import access_expiry, create_signed_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models import (
    AIConversation,
    AIMessage,
    AIUsageRecord,
    AuthSession,
    BusinessKnowledge,
    Organization,
    OrganizationMember,
    User,
)
from app.models.enums import OrganizationRole
from app.services.ai_providers import (
    AIProviderError,
    GeminiTextProvider,
    GeneratedText,
    OpenAITextProvider,
    _provider_error,
    generate_text,
)

pytestmark = pytest.mark.anyio


class AIRedis:
    def __init__(self) -> None:
        self.eval_result = 1
        self.calls = 0

    async def eval(self, *_args) -> int:
        self.calls += 1
        return self.eval_result

    async def aclose(self) -> None:
        return None


@pytest.fixture
def ai_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://test_user@localhost:5432/test_db",
        redis_url="redis://localhost:6379/15",
        cors_allowed_origins=["http://test"],
        jwt_secret_key="test-key-for-ai-integration-000000000000000000",
        openai_api_key="fake-openai-key",
        gemini_api_key="fake-gemini-key",
        ai_daily_request_limit=10,
        ai_requests_per_minute=5,
    )


@pytest.fixture
async def ai_client(monkeypatch: pytest.MonkeyPatch, ai_settings: Settings):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_session():
        async with session_factory() as session:
            yield session

    redis = AIRedis()
    monkeypatch.setattr(Redis, "from_url", lambda *_args, **_kwargs: redis)
    app = create_app(ai_settings)
    app.dependency_overrides[get_db_session] = override_session
    async with session_factory() as session:
        user = User(
            name="AI Test User",
            email="ai-test@example.com",
            password_hash="not-used-by-ai-tests",
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        organization = Organization(
            name="AI Test Workspace",
            slug="ai-test-workspace",
            owner_user_id=user.id,
        )
        session.add(organization)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
        )
        auth_session = AuthSession(
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(auth_session)
        await session.commit()
        access_token, _ = create_signed_token(
            ai_settings,
            subject=user.id,
            token_use="access",
            expires_at=access_expiry(ai_settings),
            extra_claims={
                "sid": str(auth_session.id),
                "org_id": str(organization.id),
                "role": OrganizationRole.OWNER.value,
                "ver": user.auth_version,
            },
        )
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            yield client, redis, session_factory, user.id, organization.id
    await engine.dispose()


async def test_openai_responses_sdk_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    import openai

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.responses = self

        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text="Draft response",
                usage=SimpleNamespace(input_tokens=17, output_tokens=8),
            )

        async def close(self) -> None:
            return None

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    result = await OpenAITextProvider().generate(
        api_key="unit-test-key",
        model="gpt-4.1-mini",
        instructions="instructions",
        prompt='{"request":"draft"}',
        max_output_tokens=90,
        timeout_seconds=2,
    )
    assert result == GeneratedText("Draft response", 17, 8)
    assert captured["store"] is False
    assert captured["max_output_tokens"] == 90


async def test_gemini_google_genai_sdk_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from google import genai

    captured: dict[str, object] = {}

    class FakeModels:
        async def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text="Suggested keywords",
                usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=5),
            )

    class FakeAsyncClient:
        models = FakeModels()

        async def aclose(self) -> None:
            return None

    class FakeClient:
        @property
        def aio(self):
            return FakeAsyncClient()

    monkeypatch.setattr(genai, "Client", lambda **_kwargs: FakeClient())
    result = await GeminiTextProvider().generate(
        api_key="unit-test-key",
        model="gemini-3.8-flash",
        instructions="instructions",
        prompt='{"request":"keywords"}',
        max_output_tokens=90,
        timeout_seconds=2,
    )
    assert result == GeneratedText("Suggested keywords", 12, 5)
    assert captured["model"] == "gemini-3.8-flash"
    assert captured["config"].max_output_tokens == 90


async def test_provider_timeout_is_bounded_and_retryable(ai_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = ai_settings.model_copy(update={"ai_request_timeout_seconds": 0.01})
    calls = 0

    class SlowProvider:
        async def generate(self, **_kwargs):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.1)

    monkeypatch.setattr("app.services.ai_providers.make_provider", lambda _provider: SlowProvider())
    with pytest.raises(AIProviderError, match="provider_timeout"):
        await generate_text(
            settings,
            provider="openai",
            model=settings.ai_openai_model,
            instructions="system",
            prompt="input",
        )
    assert calls == 2


def test_provider_rate_limit_and_server_errors_are_retryable() -> None:
    assert _provider_error(SimpleNamespace(status_code=429)).retryable
    assert _provider_error(SimpleNamespace(status_code=503)).category == "provider_temporarily_unavailable"
    assert not _provider_error(SimpleNamespace(status_code=400)).retryable


def test_gemini_sdk_code_and_openai_connection_errors_are_retryable() -> None:
    from google.genai.errors import APIError
    from openai import APIConnectionError, APITimeoutError

    rate_limit = _provider_error(APIError(429, {"error": {"message": "rate limited"}}))
    unavailable = _provider_error(APIError(503, {"error": {"message": "unavailable"}}))
    connection = _provider_error(APIConnectionError(request=SimpleNamespace()))
    timeout = _provider_error(APITimeoutError(request=SimpleNamespace()))

    assert rate_limit.category == "provider_rate_limited"
    assert rate_limit.retryable
    assert unavailable.category == "provider_temporarily_unavailable"
    assert unavailable.retryable
    assert connection.retryable
    assert timeout.category == "provider_timeout"
    assert timeout.retryable


async def test_provider_selection_chat_storage_and_usage_tracking(ai_client, monkeypatch) -> None:
    client, redis, sessions, _, organization_id = ai_client

    async def fake_generate(_settings, *, selection, purpose, payload):
        assert selection.provider == "openai"
        assert purpose == "chat"
        assert payload["task"]
        return GeneratedText("Use the automation settings page to configure it.", 30, 12)

    monkeypatch.setattr(ai_api, "generate", fake_generate)
    settings_response = await client.get("/api/v1/ai/providers")
    assert settings_response.status_code == 200
    assert settings_response.json()["selected_provider"] == "openai"
    assert "fake-openai-key" not in settings_response.text
    assert "fake-gemini-key" not in settings_response.text

    response = await client.post("/api/v1/ai/chat", json={"message": "How do I set up an automation?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"].startswith("Use the automation settings")
    assert body["input_tokens"] == 30
    async with sessions() as session:
        conversation = await session.get(AIConversation, UUID(body["conversation_id"]))
        messages = list(
            (
                await session.scalars(
                    select(AIMessage).where(AIMessage.conversation_id == UUID(body["conversation_id"]))
                )
            ).all()
        )
        usage = list((await session.scalars(select(AIUsageRecord))).all())
        assert conversation.organization_id == organization_id
        assert [item.role for item in messages] == ["user", "assistant"]
        assert len(usage) == 1
        assert usage[0].request_status == "succeeded"
        assert usage[0].input_tokens == 30
    assert redis.calls == 1


async def test_knowledge_and_conversations_are_organization_isolated(ai_client, monkeypatch) -> None:
    client, _redis, sessions, user_id, organization_id = ai_client
    foreign_org_id = uuid4()
    foreign_conversation_id = uuid4()
    async with sessions() as session:
        foreign_org = Organization(
            id=foreign_org_id,
            name="Other Workspace",
            slug="other-ai-workspace",
            owner_user_id=user_id,
        )
        session.add(foreign_org)
        session.add(
            BusinessKnowledge(
                organization_id=foreign_org_id,
                business_name="Foreign Secret Business",
                description="foreign-only knowledge",
            )
        )
        session.add(
            AIConversation(
                id=foreign_conversation_id,
                organization_id=foreign_org_id,
                title="Foreign conversation",
            )
        )
        session.add(
            BusinessKnowledge(
                organization_id=organization_id,
                business_name="Current Tenant Shop",
                description="Tenant-owned description",
            )
        )
        await session.commit()

    async def fake_generate(_settings, *, selection, purpose, payload):
        assert "Current Tenant Shop" in str(payload)
        assert "Foreign Secret Business" not in str(payload)
        return GeneratedText("Tenant-specific answer.", 11, 4)

    monkeypatch.setattr(ai_api, "generate", fake_generate)
    knowledge = await client.get("/api/v1/ai/knowledge")
    assert knowledge.status_code == 200
    assert knowledge.json()["business_name"] == "Current Tenant Shop"
    foreign = await client.get(f"/api/v1/ai/conversations/{foreign_conversation_id}")
    assert foreign.status_code == 404
    listed = await client.get("/api/v1/ai/conversations")
    assert foreign_conversation_id not in {item["id"] for item in listed.json()}
    response = await client.post("/api/v1/ai/chat", json={"message": "What does this business sell?"})
    assert response.status_code == 200, response.text


async def test_assist_validation_provider_failure_and_failed_usage(ai_client, monkeypatch) -> None:
    client, _redis, sessions, _, _ = ai_client
    invalid = await client.post(
        "/api/v1/ai/assist",
        json={"action": "translate", "input_text": "hello"},
    )
    assert invalid.status_code == 422
    too_long = await client.post(
        "/api/v1/ai/assist",
        json={"action": "draft_message", "input_text": "x" * 12_001},
    )
    assert too_long.status_code == 422

    async def fail_provider(*_args, **_kwargs):
        raise AIProviderError("provider_temporarily_unavailable", retryable=True)

    monkeypatch.setattr(ai_api, "generate", fail_provider)
    failed = await client.post(
        "/api/v1/ai/assist",
        json={"action": "suggest_keywords", "input_text": "Social post about a new product"},
    )
    assert failed.status_code == 502
    async with sessions() as session:
        usage = list((await session.scalars(select(AIUsageRecord))).all())
        assert len(usage) == 1
        assert usage[0].request_status == "failed"


async def test_organization_ai_daily_limit_is_enforced(ai_client) -> None:
    client, redis, _sessions, _, _ = ai_client
    redis.eval_result = -2
    response = await client.post(
        "/api/v1/ai/assist",
        json={"action": "draft_message", "input_text": "Draft a polite reply."},
    )
    assert response.status_code == 429
    assert "daily" in response.json()["error"]["message"].lower()


async def test_provider_selection_rejects_unconfigured_provider(ai_client) -> None:
    client, _redis, _sessions, _, _ = ai_client
    response = await client.put(
        "/api/v1/ai/providers",
        json={"provider": "gemini", "model": "unconfigured-model"},
    )
    assert response.status_code == 422


async def test_provider_preference_and_knowledge_can_be_updated(ai_client) -> None:
    client, _redis, _sessions, _, _ = ai_client
    selected = await client.put(
        "/api/v1/ai/providers",
        json={"provider": "gemini", "model": "gemini-3.8-flash"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["selected_provider"] == "gemini"
    saved = await client.put(
        "/api/v1/ai/knowledge",
        json={
            "business_name": "Acme Studio",
            "description": "A customer-entered business profile.",
            "products_services": "Consulting",
            "faqs": "Q: Hours? A: Weekdays.",
            "website_information": "Customer supplied notes.",
            "custom_instructions": "Use a friendly tone.",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["business_name"] == "Acme Studio"
    assert saved.json()["updated_at"] is not None
