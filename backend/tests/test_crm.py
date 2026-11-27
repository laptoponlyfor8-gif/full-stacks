from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import crm as crm_api
from app.core.config import Settings
from app.core.security import access_expiry, create_signed_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models import (
    Automation,
    AutomationExecution,
    AuthSession,
    Contact,
    LeadActivity,
    LeadActivity,
    Message,
    MessageDeliveryAttempt,
    Organization,
    OrganizationMember,
    SocialAccount,
    User,
    WebhookEvent,
)
from app.models.enums import AutomationStatus, LeadStatus, OrganizationRole, SocialPlatform
from app.services.automation_engine import PermanentMetaError
from app.services.automation_engine import process_webhook_event

pytestmark = pytest.mark.anyio


class FakeRedis:
    async def aclose(self) -> None:
        return None


@pytest.fixture
async def crm_client(monkeypatch: pytest.MonkeyPatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://test_user@localhost:5432/test_db",
        redis_url="redis://localhost:6379/15",
        cors_allowed_origins=["http://test"],
        jwt_secret_key="test-key-for-crm-integration-000000000000000000",
        meta_graph_api_version="v27.0",
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def override_session():
        async with factory() as session:
            yield session

    monkeypatch.setattr(Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())
    app = create_app(settings)
    app.dependency_overrides[get_db_session] = override_session
    async with factory() as session:
        user = User(
            name="CRM Owner",
            email="crm-owner@example.com",
            password_hash="not-used-by-crm-tests",
            email_verified=True,
        )
        session.add(user)
        await session.flush()
        organization = Organization(name="CRM Workspace", slug="crm-workspace", owner_user_id=user.id)
        session.add(organization)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
        )
        auth_session = AuthSession(user_id=user.id, expires_at=datetime.now(UTC) + timedelta(hours=1))
        session.add(auth_session)
        await session.commit()
        token, _ = create_signed_token(
            settings,
            subject=user.id,
            token_use="access",
            expires_at=access_expiry(settings),
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
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, factory, organization.id, user.id
    await engine.dispose()


async def _seed_account(factory, organization_id, *, encrypted_token=None):
    async with factory() as session:
        account = SocialAccount(
            organization_id=organization_id,
            platform=SocialPlatform.INSTAGRAM,
            platform_account_id=f"ig-{uuid4()}",
            account_name="Connected Instagram",
            is_connected=True,
            encrypted_access_token=encrypted_token,
        )
        session.add(account)
        await session.commit()
        return account.id


async def test_crm_contacts_notes_tags_lead_status_and_isolation(crm_client):
    client, factory, organization_id, user_id = crm_client
    account_id = await _seed_account(factory, organization_id)
    response = await client.post(
        "/api/v1/contacts",
        json={
            "social_account_id": str(account_id),
            "platform_customer_id": "customer-101",
            "display_name": "Asha",
            "custom_fields": {"source": "instagram"},
        },
    )
    assert response.status_code == 201
    contact = response.json()
    contact_id = contact["id"]
    assert contact["platform_customer_id"] == "customer-101"
    assert contact["custom_fields"] == {"source": "instagram"}
    changed_contact = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        json={"display_name": "Asha K", "custom_fields": {"source": "instagram", "tier": "gold"}},
    )
    assert changed_contact.status_code == 200
    assert changed_contact.json()["display_name"] == "Asha K"
    assert changed_contact.json()["custom_fields"]["tier"] == "gold"

    note = await client.post(
        f"/api/v1/contacts/{contact_id}/notes",
        json={"content": "Asked for the product catalogue."},
    )
    assert note.status_code == 201
    assert note.json()["author_user_id"] == str(user_id)

    tag = await client.post("/api/v1/tags", json={"name": "Interested"})
    assert tag.status_code == 201
    updated = await client.put(
        f"/api/v1/contacts/{contact_id}/tags",
        json={"tag_ids": [tag.json()["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json()["tags"] == ["Interested"]

    changed = await client.patch(
        f"/api/v1/leads/{contact_id}/status",
        json={"status": "qualified"},
    )
    assert changed.status_code == 200
    assert changed.json()["lead_status"] == LeadStatus.QUALIFIED.value
    activities = await client.get(f"/api/v1/leads/{contact_id}/activities")
    assert activities.status_code == 200
    assert activities.json()[0]["detail"] == "new->qualified"

    contacts = await client.get("/api/v1/contacts?limit=1")
    assert contacts.status_code == 200
    assert contacts.json()["total"] == 1
    assert len(contacts.json()["items"]) == 1
    notes = await client.get(f"/api/v1/contacts/{contact_id}/notes")
    assert notes.json()[0]["content"] == "Asked for the product catalogue."

    async with factory() as session:
        foreign_org = Organization(name="Other", slug=f"other-{uuid4()}", owner_user_id=user_id)
        session.add(foreign_org)
        await session.flush()
        foreign_account = SocialAccount(
            organization_id=foreign_org.id,
            platform=SocialPlatform.FACEBOOK,
            platform_account_id=f"fb-{uuid4()}",
            account_name="Other account",
            is_connected=True,
        )
        session.add(foreign_account)
        await session.flush()
        foreign_contact = Contact(
            organization_id=foreign_org.id,
            social_account_id=foreign_account.id,
            platform_customer_id="private-customer",
            display_name="Private",
        )
        session.add(foreign_contact)
        await session.commit()
        foreign_contact_id = foreign_contact.id

    isolated = await client.get(f"/api/v1/contacts/{foreign_contact_id}")
    assert isolated.status_code == 404
    assert (await client.get("/api/v1/contacts?q=private-customer")).json()["total"] == 0


async def test_member_can_add_notes_but_cannot_manage_lead_status(crm_client):
    client, factory, organization_id, user_id = crm_client
    account_id = await _seed_account(factory, organization_id)
    async with factory() as session:
        contact = Contact(
            organization_id=organization_id,
            social_account_id=account_id,
            platform_customer_id="member-contact",
        )
        session.add(contact)
        member = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        assert member is not None
        member.role = OrganizationRole.MEMBER
        await session.commit()
        contact_id = contact.id

    denied = await client.patch(
        f"/api/v1/leads/{contact_id}/status",
        json={"status": "qualified"},
    )
    assert denied.status_code == 403
    note = await client.post(
        f"/api/v1/contacts/{contact_id}/notes",
        json={"content": "Member note"},
    )
    assert note.status_code == 201


async def test_inbox_pagination_and_real_analytics(crm_client):
    client, factory, organization_id, _ = crm_client
    account_id = await _seed_account(factory, organization_id)
    async with factory() as session:
        now = datetime.now(UTC)
        contact = Contact(
            organization_id=organization_id,
            social_account_id=account_id,
            platform_customer_id="customer-inbox",
            display_name="Inbox customer",
            first_contact_at=now - timedelta(minutes=5),
            last_interaction_at=now,
            lead_status=LeadStatus.CONVERTED.value,
            updated_at=now,
        )
        session.add(contact)
        await session.flush()
        session.add(
            LeadActivity(
                organization_id=organization_id,
                contact_id=contact.id,
                activity_type="status_changed",
                detail="qualified->converted",
                created_at=now,
            )
        )
        automation = Automation(
            organization_id=organization_id,
            social_account_id=account_id,
            name="Confirmed automation",
            content_url="",
            platform_content_id="",
            trigger_type="comment",
            content_type="Instagram Post",
            status=AutomationStatus.ACTIVE,
        )
        event = WebhookEvent(
            organization_id=organization_id,
            social_account_id=account_id,
            platform="instagram",
            event_type="comment",
            idempotency_key="a" * 64,
            payload={},
            available_at=now,
        )
        session.add_all([automation, event])
        await session.flush()
        session.add(
            AutomationExecution(
                organization_id=organization_id,
                webhook_event_id=event.id,
                automation_id=automation.id,
                status="sent",
                started_at=now,
            )
        )
        session.add_all(
            [
                Message(
                    organization_id=organization_id,
                    social_account_id=account_id,
                    contact_id=contact.id,
                    recipient_platform_id=contact.platform_customer_id,
                    message_type="incoming",
                    message_content="Hello",
                    delivery_status="received",
                    external_message_id="in-1",
                    platform_created_at=now - timedelta(minutes=4),
                    is_read=False,
                ),
                Message(
                    organization_id=organization_id,
                    social_account_id=account_id,
                    contact_id=contact.id,
                    recipient_platform_id=contact.platform_customer_id,
                    message_type="manual",
                    message_content="Confirmed reply",
                    delivery_status="sent",
                    external_message_id="out-1",
                    platform_created_at=now,
                    is_read=True,
                ),
            ]
        )
        await session.commit()
        contact_id = contact.id

    inbox = await client.get("/api/v1/conversations?limit=1")
    assert inbox.status_code == 200
    assert inbox.json()["total"] == 1
    assert inbox.json()["items"][0]["unread_count"] == 1
    detail = await client.get(f"/api/v1/conversations/{contact_id}")
    assert detail.status_code == 200
    assert [message["message_type"] for message in detail.json()["messages"]] == ["incoming", "manual"]
    assert (await client.patch(f"/api/v1/conversations/{contact_id}/read")).status_code == 204
    refreshed = await client.get("/api/v1/conversations")
    assert refreshed.json()["items"][0]["unread_count"] == 0

    analytics = await client.get("/api/v1/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["messages_received"]["value"] == 1
    assert analytics.json()["messages_sent"]["value"] == 1
    assert analytics.json()["total_contacts"]["value"] == 1
    assert analytics.json()["active_automations"]["value"] == 1
    assert analytics.json()["automation_executions"]["value"] == 1
    assert analytics.json()["successful_executions"]["value"] == 1
    assert analytics.json()["converted_leads"]["value"] == 1
    assert analytics.json()["platform_breakdown"] == [{"platform": "instagram", "sent": 1, "received": 1}]
    assert analytics.json()["daily_messages"]


@pytest.mark.parametrize(
    ("failure_category", "expected_status"),
    [("provider_rejected", "failed"), ("delivery_outcome_unknown", "uncertain")],
)
async def test_manual_send_failure_is_not_reported_as_sent(
    monkeypatch, crm_client, failure_category, expected_status
):
    client, factory, organization_id, _ = crm_client
    account_id = await _seed_account(factory, organization_id, encrypted_token="ciphertext")
    async with factory() as session:
        contact = Contact(
            organization_id=organization_id,
            social_account_id=account_id,
            platform_customer_id="customer-reply",
        )
        session.add(contact)
        await session.flush()
        inbound = Message(
            organization_id=organization_id,
            social_account_id=account_id,
            contact_id=contact.id,
            recipient_platform_id=contact.platform_customer_id,
            message_type="incoming",
            message_content="Hi",
            delivery_status="received",
            external_message_id="incoming-reply",
            platform_created_at=datetime.now(UTC) - timedelta(minutes=2),
            is_read=False,
        )
        session.add(inbound)
        await session.commit()
        contact_id = contact.id

    monkeypatch.setattr(crm_api, "decrypt_token", lambda *_args, **_kwargs: "test-token")

    async def fail_send(*_args, **_kwargs):
        raise PermanentMetaError(failure_category)

    monkeypatch.setattr(crm_api, "send_meta_text", fail_send)
    response = await client.post(
        f"/api/v1/conversations/{contact_id}/messages",
        json={"text": "A real reply", "idempotency_key": "client-request-123"},
    )
    assert response.status_code == 502
    async with factory() as session:
        message = await session.scalar(
            select(Message).where(Message.idempotency_key.like("manual:%"))
        )
        assert message is not None
        assert message.delivery_status == expected_status
        attempt = await session.scalar(
            select(MessageDeliveryAttempt).where(MessageDeliveryAttempt.message_id == message.id)
        )
        assert attempt is not None
        assert attempt.status == "failed"

    duplicate = await client.post(
        f"/api/v1/conversations/{contact_id}/messages",
        json={"text": "A real reply", "idempotency_key": "client-request-123"},
    )
    assert duplicate.status_code == 409


async def test_old_incoming_meta_message_is_stored_but_not_automated(crm_client):
    _, factory, organization_id, _ = crm_client
    account_id = await _seed_account(factory, organization_id)
    event_time_ms = int((datetime.now(UTC) - timedelta(days=30)).timestamp() * 1000)
    async with factory() as session:
        event = WebhookEvent(
            organization_id=organization_id,
            social_account_id=account_id,
            platform="instagram",
            event_type="direct_message",
            idempotency_key="b" * 64,
            payload={
                "message_id": "old-direct-message",
                "text": "A message outside the reply window",
                "actor_id": "customer-old-message",
                "timestamp": event_time_ms,
            },
            available_at=datetime.now(UTC),
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with factory() as session:
        await process_webhook_event(session, None, event_id, organization_id)
        event = await session.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id))
        message = await session.scalar(
            select(Message).where(Message.external_message_id == "old-direct-message")
        )
        contact = await session.scalar(
            select(Contact).where(Contact.platform_customer_id == "customer-old-message")
        )
        assert event is not None
        assert event.processing_status == "ignored"
        assert event.error_category == "outside_messaging_window"
        assert message is not None
        assert message.delivery_status == "received"
        assert contact is not None
