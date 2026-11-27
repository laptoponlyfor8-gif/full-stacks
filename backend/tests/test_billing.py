from __future__ import annotations

import hashlib
import hmac
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import access_expiry, create_signed_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models import (
    AuthSession,
    BillingPlan,
    BillingWebhookEvent,
    Organization,
    OrganizationMember,
    OrganizationRole,
    Payment,
    Subscription,
    User,
)
from app.services.razorpay import RazorpayError, verify_checkout_signature, verify_webhook_signature

pytestmark = pytest.mark.anyio

KEY_SECRET = "test-key-secret-not-for-production"
WEBHOOK_SECRET = "test-webhook-secret"
SUBSCRIPTION_ID = "sub_0123456789abcd"
PAYMENT_ID = "pay_0123456789abcd"


class BillingRedis:
    def __init__(self) -> None:
        self.counts: defaultdict[str, int] = defaultdict(int)

    async def eval(self, _script: str, _num_keys: int, key: str, _window: int) -> int:
        self.counts[key] += 1
        return self.counts[key]

    async def aclose(self) -> None:
        return None


class FakeRazorpay:
    def __init__(self, organization_id: UUID) -> None:
        self.organization_id = organization_id
        self.plan_creations = 0
        self.customer_creations = 0
        self.subscription_creations = 0
        self.next_subscription_id = SUBSCRIPTION_ID
        self.cancel_calls: list[tuple[str, bool]] = []
        self.subscription_status = "created"
        self.plan_error: RazorpayError | None = None
        self.create_error: RazorpayError | None = None
        self.last_subscription_request: dict | None = None

    async def create_plan(self) -> dict:
        self.plan_creations += 1
        if self.plan_error:
            raise self.plan_error
        return {"id": "plan_0123456789abcd"}

    async def create_customer(self, **_kwargs) -> dict:
        self.customer_creations += 1
        return {"id": "cust_0123456789abcd"}

    async def create_subscription(self, **kwargs) -> dict:
        self.subscription_creations += 1
        self.last_subscription_request = kwargs
        if self.create_error:
            raise self.create_error
        return {
            "id": self.next_subscription_id,
            "plan_id": kwargs["plan_id"],
            "status": self.subscription_status,
            "short_url": "https://rzp.io/test",
            "charge_at": 1_800_000_000,
        }

    async def fetch_payment(self, payment_id: str) -> dict:
        return {
            "id": payment_id,
            "subscription_id": SUBSCRIPTION_ID,
            "amount": 29900,
            "currency": "INR",
            "status": "captured",
            "created_at": 1_700_000_000,
        }

    async def fetch_subscription(self, subscription_id: str) -> dict:
        return {
            "id": subscription_id,
            "plan_id": "plan_0123456789abcd",
            "status": self.subscription_status,
            "notes": {"organization_id": str(self.organization_id)},
            "customer_id": "cust_0123456789abcd",
            "current_start": 1_700_000_000,
            "current_end": 1_702_592_000,
            "charge_at": 1_702_592_000,
        }

    async def cancel_subscription(self, subscription_id: str, *, cancel_at_cycle_end: bool) -> dict:
        self.cancel_calls.append((subscription_id, cancel_at_cycle_end))
        return {"id": subscription_id, "status": self.subscription_status}


@pytest.fixture
def billing_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://test_user@localhost:5432/test_db",
        redis_url="redis://localhost:6379/15",
        cors_allowed_origins=["http://test"],
        jwt_secret_key="billing-test-secret-key-long-enough-for-validation",
        auth_sensitive_rate_limit=100,
        webhook_rate_limit_per_minute=100,
        razorpay_key_id="rzp_test_key_id",
        razorpay_key_secret=KEY_SECRET,
        razorpay_webhook_secret=WEBHOOK_SECRET,
    )


@pytest.fixture
async def billing_client(monkeypatch: pytest.MonkeyPatch, billing_settings: Settings):
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

    redis = BillingRedis()
    monkeypatch.setattr(Redis, "from_url", lambda *_args, **_kwargs: redis)
    app = create_app(billing_settings)
    app.dependency_overrides[get_db_session] = override_session
    async with session_factory() as session:
        user = User(
            name="Billing Owner",
            email="billing-owner@example.test",
            password_hash="not-used-in-billing-tests",
            mobile_number="+919876543210",
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        organization = Organization(
            name="Billing Workspace",
            slug="billing-workspace",
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
        token, _ = create_signed_token(
            billing_settings,
            subject=user.id,
            token_use="access",
            expires_at=access_expiry(billing_settings),
            extra_claims={
                "sid": str(auth_session.id),
                "org_id": str(organization.id),
                "role": OrganizationRole.OWNER.value,
                "ver": user.auth_version,
            },
        )
        fake_provider = FakeRazorpay(organization.id)
    app.state.razorpay_client = fake_provider
    headers = {"Authorization": f"Bearer {token}"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client, headers, session_factory, fake_provider, user, organization, auth_session
    await engine.dispose()


def _signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _checkout_signature() -> str:
    return hmac.new(
        KEY_SECRET.encode(),
        f"{SUBSCRIPTION_ID}|{PAYMENT_ID}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _webhook(
    *,
    event_type: str,
    organization_id: UUID,
    status_value: str = "active",
    created_at: int = 1_700_000_000,
    payment_status: str = "captured",
    local_subscription_id: UUID | None = None,
) -> bytes:
    notes = {"organization_id": str(organization_id)}
    if local_subscription_id is not None:
        notes["dm_karo_subscription_id"] = str(local_subscription_id)
    envelope = {
        "event": event_type,
        "created_at": created_at,
        "payload": {
            "subscription": {
                "entity": {
                    "id": SUBSCRIPTION_ID,
                    "plan_id": "plan_0123456789abcd",
                    "status": status_value,
                    "customer_id": "cust_0123456789abcd",
                    "notes": notes,
                    "current_start": 1_700_000_000,
                    "current_end": 1_702_592_000,
                    "charge_at": 1_702_592_000,
                }
            },
            "payment": {
                "entity": {
                    "id": PAYMENT_ID,
                    "subscription_id": SUBSCRIPTION_ID,
                    "amount": 29900,
                    "currency": "INR",
                    "status": payment_status,
                }
            },
        },
    }
    return json.dumps(envelope, separators=(",", ":")).encode()


async def _create_subscription(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert response.status_code == 201, response.text
    return response.json()


async def test_subscription_creation_is_idempotent_for_plan_customer_and_open_subscription(
    billing_client,
) -> None:
    client, headers, session_factory, provider, _, organization, _ = billing_client
    created = await _create_subscription(client, headers)
    assert created["key_id"] == "rzp_test_key_id"
    assert created["subscription_id"] == SUBSCRIPTION_ID
    assert created["status"] == "created"
    assert "secret" not in created
    assert provider.plan_creations == 1
    assert provider.customer_creations == 1

    duplicate = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert duplicate.status_code == 409
    assert provider.subscription_creations == 1

    async with session_factory() as session:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.organization_id == organization.id)
        )
        assert subscription is not None
        subscription.status = "cancelled"
        await session.commit()
    provider.subscription_status = "created"
    provider.next_subscription_id = "sub_1123456789abcd"
    renewed = await _create_subscription(client, headers)
    assert renewed["status"] == "created"
    assert provider.plan_creations == 1
    assert provider.customer_creations == 1


async def test_existing_legacy_subscription_does_not_block_razorpay_checkout(billing_client) -> None:
    client, headers, session_factory, _, _user, organization, _ = billing_client
    async with session_factory() as session:
        session.add(
            Subscription(
                organization_id=organization.id,
                plan_name="Legacy preview",
                amount=Decimal("0.00"),
                currency="INR",
                status="active",
            )
        )
        await session.commit()
    created = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert created.status_code == 201, created.text


async def test_checkout_signature_is_verified_and_payment_waits_for_activation_webhook(
    billing_client,
) -> None:
    client, headers, session_factory, _, _, organization, _ = billing_client
    await _create_subscription(client, headers)

    invalid = await client.post(
        "/api/v1/billing/checkout/verify",
        headers=headers,
        json={
            "razorpay_payment_id": PAYMENT_ID,
            "razorpay_subscription_id": SUBSCRIPTION_ID,
            "razorpay_signature": "0" * 64,
        },
    )
    assert invalid.status_code == 400

    verified = await client.post(
        "/api/v1/billing/checkout/verify",
        headers=headers,
        json={
            "razorpay_payment_id": PAYMENT_ID,
            "razorpay_subscription_id": SUBSCRIPTION_ID,
            "razorpay_signature": _checkout_signature(),
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True
    assert verified.json()["subscription_status"] == "created"
    assert "when Razorpay confirms activation" in verified.json()["message"]
    history = await client.get("/api/v1/billing/payments", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["status"] == "captured"
    assert history.json()[0]["amount"] == "299.00"

    async with session_factory() as session:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.organization_id == organization.id)
        )
        payment_count = await session.scalar(select(func.count()).select_from(Payment))
        assert subscription.status == "created"
        assert payment_count == 1


async def test_webhook_signature_idempotency_and_authoritative_status_processing(
    billing_client,
) -> None:
    client, headers, session_factory, _, _, organization, _ = billing_client
    await _create_subscription(client, headers)
    body = _webhook(event_type="subscription.activated", organization_id=organization.id)
    invalid = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "0" * 64, "X-Razorpay-Event-Id": "evt-invalid"},
    )
    assert invalid.status_code == 400

    webhook_headers = {
        "X-Razorpay-Signature": _signature(WEBHOOK_SECRET, body),
        "X-Razorpay-Event-Id": "evt-test-activation-0001",
    }
    response = await client.post("/api/v1/webhooks/razorpay", content=body, headers=webhook_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    duplicate = await client.post("/api/v1/webhooks/razorpay", content=body, headers=webhook_headers)
    assert duplicate.json()["status"] == "duplicate"

    async with session_factory() as session:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.organization_id == organization.id)
        )
        event_count = await session.scalar(select(func.count()).select_from(BillingWebhookEvent))
        payment_count = await session.scalar(select(func.count()).select_from(Payment))
        assert subscription.status == "active"
        assert event_count == 1
        assert payment_count == 1


async def test_out_of_order_webhook_does_not_regress_status_and_payment_failure_is_recorded(
    billing_client,
) -> None:
    client, headers, session_factory, _, _, organization, _ = billing_client
    await _create_subscription(client, headers)
    active_body = _webhook(
        event_type="subscription.activated",
        organization_id=organization.id,
        created_at=1_700_000_100,
    )
    await client.post(
        "/api/v1/webhooks/razorpay",
        content=active_body,
        headers={
            "X-Razorpay-Signature": _signature(WEBHOOK_SECRET, active_body),
            "X-Razorpay-Event-Id": "evt-newer-activation",
        },
    )
    failed_body = _webhook(
        event_type="subscription.pending",
        organization_id=organization.id,
        status_value="pending",
        created_at=1_700_000_200,
        payment_status="failed",
    )
    failed = await client.post(
        "/api/v1/webhooks/razorpay",
        content=failed_body,
        headers={
            "X-Razorpay-Signature": _signature(WEBHOOK_SECRET, failed_body),
            "X-Razorpay-Event-Id": "evt-newer-payment-failure",
        },
    )
    assert failed.status_code == 200
    payment_failed_body = _webhook(
        event_type="payment.failed",
        organization_id=organization.id,
        status_value="pending",
        created_at=1_700_000_300,
        payment_status="failed",
    )
    payment_failed = await client.post(
        "/api/v1/webhooks/razorpay",
        content=payment_failed_body,
        headers={
            "X-Razorpay-Signature": _signature(WEBHOOK_SECRET, payment_failed_body),
            "X-Razorpay-Event-Id": "evt-payment-failed",
        },
    )
    assert payment_failed.status_code == 200
    older_active_body = _webhook(
        event_type="subscription.activated",
        organization_id=organization.id,
        created_at=1_700_000_050,
        payment_status="captured",
    )
    stale = await client.post(
        "/api/v1/webhooks/razorpay",
        content=older_active_body,
        headers={
            "X-Razorpay-Signature": _signature(WEBHOOK_SECRET, older_active_body),
            "X-Razorpay-Event-Id": "evt-stale-activation",
        },
    )
    assert stale.status_code == 200

    async with session_factory() as session:
        subscription = await session.scalar(select(Subscription))
        payment = await session.scalar(select(Payment))
        assert subscription.status == "pending"
        assert payment.status == "failed"
        assert subscription.grace_period_ends_at is not None


async def test_cancellation_and_payment_history_are_organization_scoped(
    billing_client,
    billing_settings: Settings,
) -> None:
    client, headers, session_factory, provider, user, organization, auth_session = billing_client
    await _create_subscription(client, headers)
    async with session_factory() as session:
        subscription = await session.scalar(select(Subscription))
        subscription.status = "active"
        await session.commit()
        subscription_id = subscription.id
        other_org = Organization(
            name="Other Workspace",
            slug="other-workspace",
            owner_user_id=user.id,
        )
        session.add(other_org)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=other_org.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
        )
        await session.commit()
        other_id = other_org.id

    other_token, _ = create_signed_token(
        billing_settings,
        subject=user.id,
        token_use="access",
        expires_at=access_expiry(billing_settings),
        extra_claims={
            "sid": str(auth_session.id),
            "org_id": str(other_id),
            "role": OrganizationRole.OWNER.value,
            "ver": user.auth_version,
        },
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}
    overview = await client.get("/api/v1/billing", headers=other_headers)
    assert overview.status_code == 200
    assert overview.json()["subscription"] is None
    denied_cancel = await client.post(
        f"/api/v1/billing/subscriptions/{subscription_id}/cancel",
        headers=other_headers,
        json={"cancel_at_cycle_end": True},
    )
    assert denied_cancel.status_code == 404

    cancelled = await client.post(
        f"/api/v1/billing/subscriptions/{subscription_id}/cancel",
        headers=headers,
        json={"cancel_at_cycle_end": True},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["cancel_at_cycle_end"] is True
    assert provider.cancel_calls == [(SUBSCRIPTION_ID, True)]
    history = await client.get("/api/v1/billing/payments", headers=other_headers)
    assert history.status_code == 200
    assert history.json() == []


async def test_billing_requires_owner_or_admin_role(
    billing_client,
    billing_settings: Settings,
) -> None:
    client, _headers, session_factory, _, user, organization, auth_session = billing_client
    async with session_factory() as session:
        membership = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization.id,
                OrganizationMember.user_id == user.id,
            )
        )
        membership.role = OrganizationRole.MEMBER
        await session.commit()
    token, _ = create_signed_token(
        billing_settings,
        subject=user.id,
        token_use="access",
        expires_at=access_expiry(billing_settings),
        extra_claims={
            "sid": str(auth_session.id),
            "org_id": str(organization.id),
            "role": OrganizationRole.MEMBER.value,
            "ver": user.auth_version,
        },
    )
    response = await client.get("/api/v1/billing", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_ambiguous_provider_failure_blocks_duplicate_subscription_creation(billing_client) -> None:
    client, headers, session_factory, provider, _user, organization, _auth_session = billing_client
    provider.create_error = RazorpayError("timeout", retryable=True)
    failed = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert failed.status_code == 503
    async with session_factory() as session:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.organization_id == organization.id)
        )
        assert subscription.status == "creation_unknown"
    duplicate = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert duplicate.status_code == 409


async def test_ambiguous_plan_creation_is_not_retried_and_cannot_duplicate_provider_plans(
    billing_client,
) -> None:
    client, headers, session_factory, provider, _user, _organization, _auth_session = billing_client
    provider.plan_error = RazorpayError("timeout", retryable=True)
    first = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert first.status_code == 503
    second = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert second.status_code == 503
    assert provider.plan_creations == 1
    async with session_factory() as session:
        plan = await session.get(BillingPlan, "dm-karo-monthly")
        assert plan.provisioning_status == "creation_unknown"


async def test_signed_webhook_recovers_subscription_after_ambiguous_create_response(
    billing_client,
) -> None:
    client, headers, session_factory, provider, _user, organization, _ = billing_client
    provider.create_error = RazorpayError("timeout", retryable=True)
    failed = await client.post("/api/v1/billing/subscriptions", headers=headers, json={})
    assert failed.status_code == 503
    async with session_factory() as session:
        pending = await session.scalar(
            select(Subscription).where(Subscription.organization_id == organization.id)
        )
        local_id = pending.id
        assert pending.status == "creation_unknown"
        assert pending.razorpay_subscription_id is None

    provider.create_error = None
    body = _webhook(
        event_type="subscription.activated",
        organization_id=organization.id,
        local_subscription_id=local_id,
    )
    recovered = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": _signature(WEBHOOK_SECRET, body),
            "X-Razorpay-Event-Id": "evt-recover-ambiguous-subscription",
        },
    )
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "accepted"
    async with session_factory() as session:
        recovered_subscription = await session.get(Subscription, local_id)
        assert recovered_subscription.razorpay_subscription_id == SUBSCRIPTION_ID
        assert recovered_subscription.status == "active"


def test_signature_verifiers_use_sha256_hmac() -> None:
    assert verify_checkout_signature(KEY_SECRET, SUBSCRIPTION_ID, PAYMENT_ID, _checkout_signature())
    body = b'{"event":"subscription.activated"}'
    assert verify_webhook_signature(WEBHOOK_SECRET, body, _signature(WEBHOOK_SECRET, body))
    assert not verify_webhook_signature(WEBHOOK_SECRET, body + b" ", _signature(WEBHOOK_SECRET, body))
