from __future__ import annotations

from collections import defaultdict
from uuid import UUID
from urllib.parse import urlparse, parse_qs

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import auth as auth_api
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models import Organization, OrganizationMember, User

pytestmark = pytest.mark.anyio


class FakeRedis:
    def __init__(self) -> None:
        self.counts: defaultdict[str, int] = defaultdict(int)

    async def eval(self, _script: str, _num_keys: int, key: str, _window: int) -> int:
        self.counts[key] += 1
        return self.counts[key]

    async def aclose(self) -> None:
        return None


class CapturingEmailProvider:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    async def send(self, recipient: str, subject: str, body: str) -> None:
        self.messages.append((recipient, subject, body))

    def latest_link_token(self, expected_path: str) -> str:
        for _, _, body in reversed(self.messages):
            for candidate in body.strip().splitlines():
                parsed = urlparse(candidate.strip())
                if parsed.path == expected_path:
                    token = parse_qs(parsed.query).get("token", [])
                    if token:
                        return token[0]
        subjects = [subject for _, subject, _ in self.messages]
        raise AssertionError(
            f"No email containing a {expected_path} token was sent; subjects: {subjects!r}."
        )


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://test_user@localhost:5432/test_db",
        redis_url="redis://localhost:6379/15",
        cors_allowed_origins=["http://test"],
        jwt_secret_key="test-key-for-authentication-only-000000000000",
        auth_login_rate_limit=100,
        auth_sensitive_rate_limit=100,
        health_check_timeout_seconds=0.1,
    )


@pytest.fixture
async def auth_client(monkeypatch: pytest.MonkeyPatch, auth_settings: Settings):
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

    fake_redis = FakeRedis()
    mailer = CapturingEmailProvider()
    monkeypatch.setattr(Redis, "from_url", lambda *_args, **_kwargs: fake_redis)
    monkeypatch.setattr(auth_api, "get_email_provider", lambda _settings: mailer)

    app = create_app(auth_settings)
    app.dependency_overrides[get_db_session] = override_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client, mailer, session_factory
    await engine.dispose()


async def register_account(client: AsyncClient, email: str = "person@example.com") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test Person",
            "business_name": "Acme Studio",
            "email": email,
            "mobile_number": "+91 98765 43210",
            "password": "Correct Horse 123!",
            "confirm_password": "Correct Horse 123!",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def verify_account(
    client: AsyncClient,
    mailer: CapturingEmailProvider,
    *,
    expected_status: int = 200,
) -> None:
    token = mailer.latest_link_token("/verify-email")
    response = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == expected_status, response.text


async def login_account(
    client: AsyncClient,
    email: str = "person@example.com",
    password: str = "Correct Horse 123!",
):
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "remember_me": True},
    )


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("dm_csrf")
    assert token
    return {"X-CSRF-Token": token}


async def test_registration_creates_user_owner_organization_and_membership(auth_client) -> None:
    client, mailer, session_factory = auth_client
    result = await register_account(client)

    assert result["email"] == "person@example.com"
    assert result["email_verification_sent"] is True
    assert "password_hash" not in result
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "person@example.com"))
        organization = await session.scalar(
            select(Organization).where(Organization.owner_user_id == user.id)
        )
        membership = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != "Correct Horse 123!"
        assert user.email_verified is False
        assert membership is not None
        assert membership.role.value == "owner"
        assert organization is not None and organization.name == "Acme Studio"
    assert mailer.messages[0][0] == "person@example.com"


async def test_duplicate_email_and_invalid_password_are_rejected(auth_client) -> None:
    client, _mailer, _session_factory = auth_client
    await register_account(client)

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Other Person",
            "business_name": "Other Studio",
            "email": "PERSON@example.com",
            "mobile_number": "9876543210",
            "password": "Correct Horse 123!",
            "confirm_password": "Correct Horse 123!",
        },
    )
    assert duplicate.status_code == 409

    invalid = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Other Person",
            "business_name": "Other Studio",
            "email": "other@example.com",
            "mobile_number": "9876543210",
            "password": "short",
            "confirm_password": "different",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["fields"]
    assert "short" not in invalid.text


async def test_login_access_validation_refresh_rotation_and_logout(auth_client) -> None:
    client, mailer, _session_factory = auth_client
    await register_account(client)
    await verify_account(client, mailer)

    invalid = await login_account(client, password="Wrong Password 123!")
    assert invalid.status_code == 401
    assert invalid.json()["error"]["message"] == "Email or password is incorrect."

    response = await login_account(client)
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    original_refresh = client.cookies.get("dm_refresh")
    assert original_refresh
    assert "httponly" in response.headers["set-cookie"].lower()

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "person@example.com"

    rotated = await client.post("/api/v1/auth/refresh", json={}, headers=csrf_headers(client))
    assert rotated.status_code == 200, rotated.text
    rotated_refresh = client.cookies.get("dm_refresh")
    assert rotated_refresh and rotated_refresh != original_refresh
    rotated_access = rotated.json()["access_token"]
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {rotated_access}"},
        )
    ).status_code == 200

    logged_out = await client.post(
        "/api/v1/auth/logout",
        headers=csrf_headers(client),
    )
    assert logged_out.status_code == 204
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {rotated_access}"},
        )
    ).status_code == 401
    assert not client.cookies.get("dm_refresh")


async def test_password_reset_is_single_use_and_revokes_existing_sessions(auth_client) -> None:
    client, mailer, session_factory = auth_client
    await register_account(client)
    await verify_account(client, mailer)
    login = await login_account(client)
    access_token = login.json()["access_token"]
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "person@example.com"))
        assert user is not None and user.is_active and user.email_verified

    forgotten = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "person@example.com"},
    )
    assert forgotten.status_code == 202
    assert forgotten.json() == {
        "message": "If an account exists for that email, password reset instructions will be sent."
    }
    reset_token = mailer.latest_link_token("/reset-password")
    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "password": "New Secure Password 456!",
            "confirm_password": "New Secure Password 456!",
        },
    )
    assert reset.status_code == 200, reset.text
    replay = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "password": "Another Secure Password 456!",
            "confirm_password": "Another Secure Password 456!",
        },
    )
    assert replay.status_code == 400
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    ).status_code == 401
    assert (await login_account(client)).status_code == 401
    assert (await login_account(client, password="New Secure Password 456!")).status_code == 200


async def test_email_verification_is_required_and_single_use(auth_client) -> None:
    client, mailer, _session_factory = auth_client
    await register_account(client)
    blocked = await login_account(client)
    assert blocked.status_code == 403
    assert blocked.headers["x-auth-error"] == "email_not_verified"
    await verify_account(client, mailer)
    assert (await login_account(client)).status_code == 200
    duplicate_verify = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": mailer.latest_link_token("/verify-email")},
    )
    assert duplicate_verify.status_code == 400


async def test_password_reset_does_not_disclose_unknown_emails(auth_client) -> None:
    client, _mailer, _session_factory = auth_client
    first = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    second = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "another@example.com"},
    )
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()


async def test_organization_membership_and_role_authorization(auth_client) -> None:
    client, mailer, session_factory = auth_client
    owner_result = await register_account(client)
    await verify_account(client, mailer)
    owner_login = await login_account(client)
    owner_token = owner_login.json()["access_token"]
    organization_id = owner_login.json()["user"]["organization"]["id"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    await register_account(client, "member@example.com")
    await verify_account(client, mailer)
    async with session_factory() as session:
        member = await session.scalar(
            select(User).where(User.email == "member@example.com")
        )
        assert member is not None
        session.add(
            OrganizationMember(
                organization_id=UUID(organization_id),
                user_id=member.id,
                role="member",
            )
        )
        await session.commit()

    member_login = await login_account(client, "member@example.com")
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}
    owner_members = await client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers=owner_headers,
    )
    assert owner_members.status_code == 200
    assert {row["role"] for row in owner_members.json()} == {"owner", "member"}

    membership = await client.get(
        f"/api/v1/organizations/{organization_id}/membership",
        headers=owner_headers,
    )
    assert membership.status_code == 200
    assert membership.json()["role"] == "owner"

    member_members = await client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers=member_headers,
    )
    assert member_members.status_code == 403
    member_access = await client.get(
        f"/api/v1/organizations/{organization_id}/membership",
        headers=member_headers,
    )
    assert member_access.status_code == 200
    assert member_access.json()["role"] == "member"


async def test_rate_limiting_is_redis_backed(auth_client, auth_settings: Settings) -> None:
    client, _mailer, _session_factory = auth_client
    auth_settings.auth_sensitive_rate_limit = 1
    first = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    second = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["retry-after"]
