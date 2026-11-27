from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import automations as automation_api, meta as meta_api
from app.core.config import Settings
from app.core.security import access_expiry, create_signed_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models import (
    AuthSession,
    Automation,
    AutomationKeyword,
    Message,
    MetaWebhookAccountRoute,
    Organization,
    OrganizationMember,
    SocialAccount,
    User,
    WebhookEvent,
)
from app.models.enums import (
    AutomationStatus,
    KeywordMatchType,
    OrganizationRole,
    SocialPlatform,
)
from app.services import automation_engine
from app.services.meta_oauth import (
    MetaProviderError,
    account_token_context,
    build_authorization_url,
    decrypt_token,
    encrypt_token,
    make_oauth_state,
    state_key,
)
from app.worker import DEAD_LETTER_STREAM, _schedule_retry

pytestmark = pytest.mark.anyio

_TEST_ENCRYPTION_KEY = base64.urlsafe_b64encode(b"unit-test-key-for-meta-oauth-32!").decode()


class OAuthRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.counts: defaultdict[str, int] = defaultdict(int)
        self.streams: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
        self.sorted_sets: dict[str, dict[str, float]] = defaultdict(dict)

    async def eval(self, _script: str, _num_keys: int, key: str, *_args) -> int:
        self.counts[key] += 1
        return self.counts[key]

    async def xadd(self, name: str, fields: dict[str, str], **_kwargs) -> str:
        self.streams[name].append(fields)
        return "1-0"

    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        self.sorted_sets[name].update(mapping)
        return len(mapping)

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def meta_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://test_user@localhost:5432/test_db",
        redis_url="redis://localhost:6379/15",
        cors_allowed_origins=["http://test"],
        jwt_secret_key="test-key-for-meta-oauth-integration-000000000000",
        meta_app_id="test-app-id",
        meta_app_secret="test-meta-app-secret",
        meta_redirect_uri="http://test/api/v1/meta/oauth/callback",
        meta_webhook_verify_token="test-webhook-verification-token",
        meta_graph_api_version="v27.0",
        meta_facebook_login_config_id="test-login-config",
        meta_token_encryption_key=_TEST_ENCRYPTION_KEY,
        auth_sensitive_rate_limit=100,
    )


@pytest.fixture
async def meta_client(monkeypatch: pytest.MonkeyPatch, meta_settings: Settings):
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

    redis = OAuthRedis()
    monkeypatch.setattr(Redis, "from_url", lambda *_args, **_kwargs: redis)

    async def subscribe(*_args, **_kwargs):
        return None

    monkeypatch.setattr(meta_api, "subscribe_account_webhooks", subscribe)
    app = create_app(meta_settings)
    app.dependency_overrides[get_db_session] = override_session
    async with session_factory() as session:
        user = User(
            name="Meta Test User",
            email="meta-user@example.com",
            password_hash="not-used-by-meta-tests",
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        organization = Organization(
            name="Meta Test Workspace",
            slug="meta-test-workspace",
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
            meta_settings,
            subject=user.id,
            token_use="access",
            expires_at=access_expiry(meta_settings),
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
            yield client, redis, session_factory, user.id, organization.id, access_token, meta_settings
    await engine.dispose()


def _oauth_state(authorization_url: str) -> str:
    return parse_qs(urlparse(authorization_url).query)["state"][0]


async def test_oauth_state_is_random_and_authorization_urls_use_supported_products(
    meta_settings: Settings,
) -> None:
    state_a, payload_a = make_oauth_state(
        user_id=uuid4(),
        organization_id=uuid4(),
        platform="instagram",
    )
    state_b, _ = make_oauth_state(
        user_id=uuid4(),
        organization_id=uuid4(),
        platform="instagram",
    )
    assert state_a != state_b
    assert json.loads(payload_a)["platform"] == "instagram"

    instagram_url = build_authorization_url(
        meta_settings,
        platform="instagram",
        state=state_a,
    )
    instagram_query = parse_qs(urlparse(instagram_url).query)
    assert urlparse(instagram_url).netloc == "www.instagram.com"
    assert instagram_query["scope"] == [
        "instagram_business_basic,instagram_business_manage_comments,instagram_business_manage_messages"
    ]
    assert instagram_query["redirect_uri"] == [meta_settings.meta_redirect_uri]

    facebook_url = build_authorization_url(
        meta_settings,
        platform="facebook",
        state=state_a,
    )
    facebook_query = parse_qs(urlparse(facebook_url).query)
    assert urlparse(facebook_url).netloc == "www.facebook.com"
    assert facebook_query["config_id"] == ["test-login-config"]
    assert facebook_query["response_type"] == ["code"]


async def test_invalid_oauth_state_and_denied_callback_are_safe(meta_client) -> None:
    client, _redis, *_ = meta_client
    invalid = await client.get(
        "/api/v1/meta/oauth/callback?state=not-a-valid-state&code=sample"
    )
    assert invalid.status_code == 303
    assert "oauth_error=invalid_state" in invalid.headers["location"]

    started = await client.post("/api/v1/meta/connect/instagram")
    state = _oauth_state(started.json()["authorization_url"])
    assert state_key(state) in _redis.values
    denied = await client.get(
        f"/api/v1/meta/oauth/callback?state={state}&error=access_denied"
    )
    assert denied.status_code == 303
    assert "oauth_error=authorization_denied" in denied.headers["location"]
    replay = await client.get(
        f"/api/v1/meta/oauth/callback?state={state}&code=unused"
    )
    assert "oauth_error=invalid_state" in replay.headers["location"]


async def test_instagram_oauth_saves_only_encrypted_token_and_lists_account(
    meta_client,
    meta_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _redis, session_factory, *_ = meta_client

    async def connect(_settings: Settings, code: str):
        assert code == "single-use-code"
        return "ig-id-123", "sample_creator", "MEDIA_CREATOR", "long-lived-token", datetime.now(UTC) + timedelta(days=60)

    monkeypatch.setattr(meta_api, "connect_instagram", connect)
    started = await client.post("/api/v1/meta/connect/instagram")
    assert started.status_code == 200
    state = _oauth_state(started.json()["authorization_url"])
    assert state_key(state) in _redis.values
    stored_state = json.loads(_redis.values[state_key(state)])
    assert stored_state["platform"] == "instagram"
    assert UUID(stored_state["user_id"]) == meta_client[3]
    assert UUID(stored_state["organization_id"]) == meta_client[4]
    async with session_factory() as session:
        membership = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == meta_client[4],
                OrganizationMember.user_id == meta_client[3],
            )
        )
        assert membership is not None
        organization = await session.scalar(select(Organization).where(Organization.id == meta_client[4]))
        assert organization is not None and organization.is_active
        assert await meta_api._authorized_organization_exists(
            session,
            user_id=meta_client[3],
            organization_id=meta_client[4],
        )
    callback = await client.get(
        f"/api/v1/meta/oauth/callback?state={state}&code=single-use-code"
    )
    assert callback.status_code == 303
    assert "oauth_status=connected" in callback.headers["location"]

    response = await client.get("/api/v1/meta/accounts")
    assert response.status_code == 200
    account_data = response.json()[0]
    assert account_data["account_name"] == "sample_creator"
    assert account_data["connection_status"] == "connected"
    assert "access_token" not in response.text
    async with session_factory() as session:
        account = await session.scalar(select(SocialAccount))
        assert account is not None
        assert account.encrypted_access_token != "long-lived-token"
        context = account_token_context(
            account.organization_id,
            account.platform.value,
            account.platform_account_id,
        )
        assert decrypt_token(meta_settings, account.encrypted_access_token, context=context) == "long-lived-token"


async def test_meta_webhook_verification_signature_and_duplicate_event_intake(meta_client) -> None:
    client, redis, sessions, _, organization_id, _, settings = meta_client
    async with sessions() as session:
        account = SocialAccount(
            organization_id=organization_id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id="ig-webhook-account",
            account_name="Webhook Account",
            is_connected=True,
        )
        session.add(account)
        await session.flush()
        session.add(
            MetaWebhookAccountRoute(
                organization_id=organization_id,
                social_account_id=account.id,
                platform="instagram",
                platform_account_id="ig-webhook-account",
            )
        )
        await session.commit()

    verified = await client.get(
        "/api/v1/webhooks/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-webhook-verification-token",
            "hub.challenge": "challenge-value",
        },
    )
    assert verified.status_code == 200
    assert verified.text == "challenge-value"
    rejected = await client.get(
        "/api/v1/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert rejected.status_code == 403

    body = json.dumps(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": "ig-webhook-account",
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "comment-idempotent-1",
                                "text": "link",
                                "media": {"id": "media-1"},
                                "from": {"id": "customer"},
                                "timestamp": datetime.now(UTC).timestamp(),
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()
    digest = hmac.new(
        settings.meta_app_secret.get_secret_value().encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    headers = {"X-Hub-Signature-256": f"sha256={digest}"}
    bad_signature = await client.post(
        "/api/v1/webhooks/meta",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=bad"},
    )
    assert bad_signature.status_code == 403
    oversized_payload = await client.post(
        "/api/v1/webhooks/meta",
        content=b"x" * 1_000_001,
    )
    assert oversized_payload.status_code == 413
    first = await client.post("/api/v1/webhooks/meta", content=body, headers=headers)
    second = await client.post("/api/v1/webhooks/meta", content=body, headers=headers)
    assert first.status_code == second.status_code == 200
    async with sessions() as session:
        events = list((await session.scalars(select(WebhookEvent))).all())
        assert len(events) == 1
        assert events[0].organization_id == organization_id
    assert redis.values == {}


async def test_real_automation_crud_activation_and_tenant_isolation(meta_client, monkeypatch) -> None:
    client, _redis, sessions, user_id, organization_id, _token, settings = meta_client
    async def resolve(_settings, **_kwargs):
        return "resolved-meta-content-id"

    monkeypatch.setattr(automation_api, "resolve_content_id", resolve)
    async with sessions() as session:
        token_context = account_token_context(organization_id, "instagram", "automation-account")
        account = SocialAccount(
            organization_id=organization_id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id="automation-account",
            account_name="Automation Account",
            encrypted_access_token=encrypt_token(settings, "private-token", context=token_context),
            is_connected=True,
        )
        session.add(account)
        await session.flush()
        foreign_org = Organization(name="Another", slug="another-org", owner_user_id=user_id)
        session.add(foreign_org)
        await session.flush()
        foreign_account = SocialAccount(
            organization_id=foreign_org.id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id="foreign-account",
            account_name="Foreign Account",
            is_connected=True,
        )
        session.add(foreign_account)
        await session.flush()
        foreign_automation = Automation(
            organization_id=foreign_org.id,
            social_account_id=foreign_account.id,
            name="Private automation",
            content_url="https://www.instagram.com/p/foreign/",
            platform_content_id="foreign-media",
            content_type="Instagram Post",
        )
        session.add(foreign_automation)
        await session.commit()
        foreign_automation_id = foreign_automation.id

    created = await client.post(
        "/api/v1/automations",
        json={
            "social_account_id": str(account.id),
            "name": "Comment reply workflow",
            "platform": "instagram",
            "content_type": "Instagram Reel",
            "content_url": "https://www.instagram.com/reel/example/",
        },
    )
    assert created.status_code == 201, created.text
    automation_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["content_url"].endswith("/reel/example/")

    configured = await client.patch(
        f"/api/v1/automations/{automation_id}",
        json={
            "keywords": [{"keyword": "LINK", "match_type": "contains"}],
            "private_reply_text": "Here is the link.",
            "status": "active",
        },
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["status"] == "active"
    assert configured.json()["keywords"] == [{"keyword": "LINK", "match_type": "contains"}]

    foreign = await client.get(f"/api/v1/automations/{foreign_automation_id}")
    assert foreign.status_code == 404
    paused = await client.patch(f"/api/v1/automations/{automation_id}", json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"


async def test_comment_event_executes_once_and_records_confirmed_meta_result(meta_client, monkeypatch) -> None:
    _client, _redis, sessions, _user_id, organization_id, _token, settings = meta_client
    send_calls = 0

    async def send(*_args, **_kwargs):
        nonlocal send_calls
        send_calls += 1
        return "meta-confirmed-message-id"

    monkeypatch.setattr(automation_engine, "send_meta_text", send)
    async with sessions() as session:
        token_context = account_token_context(organization_id, "instagram", "worker-account")
        account = SocialAccount(
            organization_id=organization_id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id="worker-account",
            account_name="Worker Account",
            encrypted_access_token=encrypt_token(settings, "worker-token", context=token_context),
            is_connected=True,
        )
        session.add(account)
        await session.flush()
        automation = Automation(
            organization_id=organization_id,
            social_account_id=account.id,
            name="Keyword response",
            content_url="https://www.instagram.com/p/worker/",
            platform_content_id="worker-media",
            content_type="Instagram Post",
            status=AutomationStatus.ACTIVE,
            private_reply_text="Here is the information.",
        )
        session.add(automation)
        await session.flush()
        session.add(
            AutomationKeyword(
                organization_id=organization_id,
                automation_id=automation.id,
                keyword="link",
                match_type=KeywordMatchType.CONTAINS,
                is_active=True,
            )
        )
        event = WebhookEvent(
            organization_id=organization_id,
            social_account_id=account.id,
            platform="instagram",
            event_type="comment",
            idempotency_key="test-comment-event-idempotency-key",
            payload={
                "comment_id": "comment-123",
                "media_id": "worker-media",
                "text": "Send the LINK please",
                "actor_id": "customer-123",
                "timestamp": datetime.now(UTC).timestamp(),
                "is_live": False,
            },
            processing_status="processing",
            available_at=datetime.now(UTC),
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with sessions() as session:
        await automation_engine.process_webhook_event(
            session,
            settings,
            event_id,
            organization_id,
        )
        messages = list((await session.scalars(select(Message))).all())
        assert len(messages) == 1
        assert messages[0].delivery_status == "sent"
        assert messages[0].external_message_id == "meta-confirmed-message-id"
        assert messages[0].message_content == "Here is the information."
    async with sessions() as session:
        await automation_engine.process_webhook_event(
            session,
            settings,
            event_id,
            organization_id,
        )
    assert send_calls == 1


async def test_worker_retries_transient_failures_and_dead_letters_after_limit(meta_client) -> None:
    _client, redis, sessions, _user_id, organization_id, _token, settings = meta_client
    settings.automation_worker_max_attempts = 2
    async with sessions() as session:
        account = SocialAccount(
            organization_id=organization_id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id="retry-account",
            account_name="Retry Account",
            is_connected=True,
        )
        session.add(account)
        await session.flush()
        event = WebhookEvent(
            organization_id=organization_id,
            social_account_id=account.id,
            platform="instagram",
            event_type="comment",
            idempotency_key="retry-event-idempotency-key",
            payload={"comment_id": "retry-comment"},
            processing_status="processing",
            available_at=datetime.now(UTC),
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    await _schedule_retry(redis, sessions, settings, event_id, organization_id, "temporary_failure")
    async with sessions() as session:
        event = await session.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id))
        assert event is not None
        assert event.retry_count == 1
        assert event.processing_status == "retry"
    await _schedule_retry(redis, sessions, settings, event_id, organization_id, "temporary_failure")
    async with sessions() as session:
        event = await session.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id))
        assert event is not None
        assert event.retry_count == 2
        assert event.processing_status == "failed"
    assert len(redis.streams[DEAD_LETTER_STREAM]) == 1

async def test_facebook_pages_are_authorization_scoped_and_disconnect_is_tenant_scoped(
    meta_client,
    meta_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _redis, session_factory, user_id, organization_id, _token, _settings = meta_client

    async def pages(_settings: Settings, code: str):
        assert code == "facebook-code"
        return [{"id": "page-1", "name": "Allowed Page", "access_token": "page-secret"}]

    async def inspect(_settings: Settings, _token: str):
        return None

    monkeypatch.setattr(meta_api, "list_facebook_pages", pages)
    monkeypatch.setattr(meta_api, "inspect_facebook_page_token", inspect)
    started = await client.post("/api/v1/meta/connect/facebook")
    state = _oauth_state(started.json()["authorization_url"])
    callback = await client.get(
        f"/api/v1/meta/oauth/callback?state={state}&code=facebook-code"
    )
    flow_id = parse_qs(urlparse(callback.headers["location"]).query)["flow_id"][0]
    available = await client.get(f"/api/v1/meta/facebook/pending/{flow_id}/pages")
    assert available.status_code == 200
    assert available.json() == [{"platform_account_id": "page-1", "account_name": "Allowed Page"}]

    saved = await client.post(
        f"/api/v1/meta/facebook/pending/{flow_id}/select",
        json={"platform_account_id": "unauthorized-page"},
    )
    assert saved.status_code == 404
    saved = await client.post(
        f"/api/v1/meta/facebook/pending/{flow_id}/select",
        json={"platform_account_id": "page-1"},
    )
    assert saved.status_code == 200
    assert "page-secret" not in saved.text

    async with session_factory() as session:
        account = await session.scalar(select(SocialAccount))
        assert account is not None and account.organization_id == organization_id

    # A different organization cannot list or disconnect this account.
    async with session_factory() as session:
        other_user = User(
            name="Other User",
            email="other-meta@example.com",
            password_hash="not-used",
            email_verified=True,
        )
        session.add(other_user)
        await session.flush()
        other_org = Organization(
            name="Other Workspace",
            slug="other-meta-workspace",
            owner_user_id=other_user.id,
        )
        session.add(other_org)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=other_org.id,
                user_id=other_user.id,
                role=OrganizationRole.OWNER,
            )
        )
        other_session = AuthSession(
            user_id=other_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(other_session)
        await session.commit()
        other_token, _ = create_signed_token(
            meta_settings,
            subject=other_user.id,
            token_use="access",
            expires_at=access_expiry(meta_settings),
            extra_claims={
                "sid": str(other_session.id),
                "org_id": str(other_org.id),
                "role": "owner",
                "ver": other_user.auth_version,
            },
        )
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert (await client.get("/api/v1/meta/accounts", headers=other_headers)).json() == []
    account_id = saved.json()["id"]
    assert (
        await client.delete(f"/api/v1/meta/accounts/{account_id}", headers=other_headers)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/meta/accounts/{account_id}")).status_code == 204
    assert (await client.get("/api/v1/meta/accounts")).json()[0]["connection_status"] == "disconnected"
    assert user_id


async def test_refresh_handles_expired_and_revoked_instagram_tokens(
    meta_client,
    meta_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _redis, session_factory, _user_id, organization_id, _access_token, _settings = meta_client
    async with session_factory() as session:
        account = SocialAccount(
            organization_id=organization_id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id="expired-ig",
            account_name="expired_creator",
            encrypted_access_token=encrypt_token(
                meta_settings,
                "expired-secret",
                context=account_token_context(organization_id, "instagram", "expired-ig"),
            ),
            token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            updated_at=datetime.now(UTC) - timedelta(days=2),
            is_connected=True,
        )
        session.add(account)
        await session.commit()
        account_id = account.id

    expired = await client.post(f"/api/v1/meta/accounts/{account_id}/refresh")
    assert expired.status_code == 409
    async with session_factory() as session:
        account = await session.scalar(select(SocialAccount).where(SocialAccount.id == account_id))
        assert account is not None and not account.is_connected and account.encrypted_access_token is None

    async with session_factory() as session:
        account = await session.scalar(select(SocialAccount).where(SocialAccount.id == account_id))
        assert account is not None
        account.is_connected = True
        account.encrypted_access_token = encrypt_token(
            meta_settings,
            "revoked-secret",
            context=account_token_context(organization_id, "instagram", "expired-ig"),
        )
        account.token_expires_at = None
        account.updated_at = datetime.now(UTC) - timedelta(days=2)
        await session.commit()

    async def rejected_refresh(_settings: Settings, _token: str):
        raise MetaProviderError(invalid_token=True)

    monkeypatch.setattr(meta_api, "refresh_instagram_token", rejected_refresh)
    rejected = await client.post(f"/api/v1/meta/accounts/{account_id}/refresh")
    assert rejected.status_code == 409
    async with session_factory() as session:
        account = await session.scalar(select(SocialAccount).where(SocialAccount.id == account_id))
        assert account is not None and not account.is_connected


async def test_token_encryption_authenticates_ciphertext(meta_settings: Settings) -> None:
    context = "org:account"
    encrypted = encrypt_token(meta_settings, "do-not-store-plaintext", context=context)
    assert encrypted.startswith("v1:")
    assert decrypt_token(meta_settings, encrypted, context=context) == "do-not-store-plaintext"
    with pytest.raises(ValueError):
        decrypt_token(meta_settings, encrypted, context="another-org")
