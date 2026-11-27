from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Automation,
    AutomationKeyword,
    AutomationStatus,
    KeywordMatchType,
    Message,
    Organization,
    OrganizationMember,
    OrganizationRole,
    SocialAccount,
    SocialPlatform,
    Subscription,
    User,
)
from app.schemas.entities import (
    AutomationCreate,
    AutomationKeywordCreate,
    AutomationRead,
    OrganizationCreate,
    OrganizationMemberRead,
    SocialAccountCreate,
    SocialAccountRead,
    SubscriptionCreate,
    SubscriptionRead,
    UserRead,
)
from app.db.base import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def create_user(name: str = "Example User", email: str = "user@example.com") -> User:
    return User(name=name, email=email, password_hash=uuid4().hex)


def create_organization(session: Session, name: str, user: User) -> Organization:
    organization = Organization(name=name, slug=name.lower(), owner=user)
    session.add(organization)
    session.flush()
    return organization


def create_account(
    session: Session,
    organization: Organization,
    platform_account_id: str,
) -> SocialAccount:
    account = SocialAccount(
        organization=organization,
        platform=SocialPlatform.INSTAGRAM,
        platform_account_id=platform_account_id,
        account_name=f"@{platform_account_id}",
    )
    session.add(account)
    session.flush()
    return account


def test_model_relationships_and_automation_keywords(db_session: Session) -> None:
    user = create_user()
    db_session.add(user)
    organization = create_organization(db_session, "acme", user)
    member = OrganizationMember(
        organization=organization,
        user=user,
        role=OrganizationRole.OWNER,
    )
    db_session.add(member)
    second_organization = create_organization(db_session, "second", user)
    second_membership = OrganizationMember(
        organization=second_organization,
        user=user,
        role=OrganizationRole.OWNER,
    )
    db_session.add(second_membership)
    account = create_account(db_session, organization, "account-1")
    automation = Automation(
        organization=organization,
        social_account=account,
        name="Welcome campaign",
        content_url="https://www.instagram.com/reel/example/",
        content_type="instagram_reel",
    )
    keyword = AutomationKeyword(
        organization=organization,
        automation=automation,
        keyword="LINK",
        match_type=KeywordMatchType.CONTAINS,
    )
    message = Message(
        organization=organization,
        automation=automation,
        social_account=account,
        recipient_platform_id="recipient-1",
        message_type="direct",
        message_content="A database record only",
        delivery_status="pending",
    )
    db_session.add_all([automation, keyword, message])
    db_session.commit()

    assert organization.owner is user
    assert member in organization.memberships
    assert second_membership in second_organization.memberships
    assert len(user.memberships) == 2
    assert automation in account.automations
    assert keyword in automation.keywords
    assert message in automation.messages
    assert message in account.messages
    assert automation.organization_id == keyword.organization_id


def test_email_is_unique_case_insensitively(db_session: Session) -> None:
    db_session.add_all(
        [
            create_user(email="Person@example.com"),
            create_user(email="person@EXAMPLE.com"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_organization_membership_is_unique(db_session: Session) -> None:
    user = create_user()
    db_session.add(user)
    organization = create_organization(db_session, "acme", user)
    db_session.add_all(
        [
            OrganizationMember(
                organization=organization,
                user=user,
                role=OrganizationRole.OWNER,
            ),
            OrganizationMember(
                organization=organization,
                user=user,
                role=OrganizationRole.ADMIN,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_cross_organization_social_account_reference_is_rejected(
    db_session: Session,
) -> None:
    first_user = create_user(email="first@example.com")
    second_user = create_user(email="second@example.com")
    db_session.add_all([first_user, second_user])
    first_org = create_organization(db_session, "first", first_user)
    second_org = create_organization(db_session, "second", second_user)
    foreign_account = create_account(db_session, second_org, "account-2")
    db_session.add(
        Automation(
            organization=first_org,
            social_account=foreign_account,
            name="Invalid cross-tenant record",
            content_url="https://www.instagram.com/p/example/",
            content_type="instagram_post",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_cross_organization_keyword_reference_is_rejected(
    db_session: Session,
) -> None:
    first_user = create_user(email="first@example.com")
    second_user = create_user(email="second@example.com")
    db_session.add_all([first_user, second_user])
    first_org = create_organization(db_session, "first", first_user)
    second_org = create_organization(db_session, "second", second_user)
    account = create_account(db_session, second_org, "account-2")
    automation = Automation(
        organization=second_org,
        social_account=account,
        name="Other tenant automation",
        content_url="https://www.instagram.com/p/example/",
        content_type="instagram_post",
    )
    db_session.add(automation)
    db_session.flush()
    db_session.add(
        AutomationKeyword(
            organization=first_org,
            automation=automation,
            keyword="LINK",
            match_type=KeywordMatchType.EXACT,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_message_must_match_automation_social_account(db_session: Session) -> None:
    user = create_user()
    db_session.add(user)
    organization = create_organization(db_session, "acme", user)
    automation_account = create_account(db_session, organization, "account-1")
    other_account = create_account(db_session, organization, "account-2")
    automation = Automation(
        organization=organization,
        social_account=automation_account,
        name="Automation",
        content_url="https://www.instagram.com/p/example/",
        content_type="instagram_post",
    )
    db_session.add(automation)
    db_session.flush()
    db_session.add(
        Message(
            organization_id=organization.id,
            automation_id=automation.id,
            social_account_id=other_account.id,
            recipient_platform_id="recipient-1",
            message_type="direct",
            message_content="Not sent",
            delivery_status="pending",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_keywords_are_case_insensitive(db_session: Session) -> None:
    user = create_user()
    db_session.add(user)
    organization = create_organization(db_session, "acme", user)
    account = create_account(db_session, organization, "account-1")
    automation = Automation(
        organization=organization,
        social_account=account,
        name="Automation",
        content_url="https://www.instagram.com/p/example/",
        content_type="instagram_post",
    )
    db_session.add(automation)
    db_session.flush()
    db_session.add_all(
        [
            AutomationKeyword(
                organization=organization,
                automation=automation,
                keyword="LINK",
                match_type=KeywordMatchType.EXACT,
            ),
            AutomationKeyword(
                organization=organization,
                automation=automation,
                keyword="link",
                match_type=KeywordMatchType.CONTAINS,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_social_account_is_rejected_within_organization(
    db_session: Session,
) -> None:
    user = create_user()
    db_session.add(user)
    organization = create_organization(db_session, "acme", user)
    db_session.add_all(
        [
            SocialAccount(
                organization=organization,
                platform=SocialPlatform.INSTAGRAM,
                platform_account_id="same-account",
                account_name="First",
            ),
            SocialAccount(
                organization=organization,
                platform=SocialPlatform.INSTAGRAM,
                platform_account_id="same-account",
                account_name="Duplicate",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_subscription_amount_constraint_is_nonnegative(db_session: Session) -> None:
    user = create_user()
    db_session.add(user)
    organization = create_organization(db_session, "acme", user)
    db_session.add(
        Subscription(
            organization_id=organization.id,
            plan_name="Single plan",
            amount=Decimal("-1.00"),
            currency="INR",
            status="pending",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_public_schemas_do_not_expose_secrets() -> None:
    assert "password_hash" not in UserRead.model_fields
    assert "encrypted_access_token" not in SocialAccountRead.model_fields


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserRead(
            id=uuid4(),
            name="Person",
            email="invalid-email",
            is_active=True,
            email_verified=False,
        )


def test_invalid_role_status_platform_and_negative_amount_are_rejected() -> None:
    with pytest.raises(ValidationError):
        OrganizationCreate(
            name="Organization",
            slug="Invalid Slug",
            owner_user_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        SocialAccountCreate(
            organization_id=uuid4(),
            platform="tiktok",
            platform_account_id="account",
            account_name="Account",
        )
    with pytest.raises(ValidationError):
        AutomationCreate(
            organization_id=uuid4(),
            social_account_id=uuid4(),
            name="Automation",
            content_url="https://example.com",
            content_type="post",
            status="running",
        )
    with pytest.raises(ValidationError):
        AutomationKeywordCreate(
            organization_id=uuid4(),
            automation_id=uuid4(),
            keyword="LINK",
            match_type="similar",
        )
    with pytest.raises(ValidationError):
        SubscriptionCreate(
            organization_id=uuid4(),
            plan_name="Plan",
            amount=Decimal("-0.01"),
            currency="INR",
            status="pending",
        )
    with pytest.raises(ValidationError):
        OrganizationMemberRead(
            id=uuid4(),
            organization_id=uuid4(),
            user_id=uuid4(),
            role="superuser",
        )
    with pytest.raises(ValidationError):
        AutomationRead(
            id=uuid4(),
            organization_id=uuid4(),
            social_account_id=uuid4(),
            name="Automation",
            content_url="https://example.com",
            content_type="post",
            status="running",
            public_reply_enabled=False,
            public_reply_text=None,
        )
    with pytest.raises(ValidationError):
        SocialAccountRead(
            id=uuid4(),
            organization_id=uuid4(),
            platform="tiktok",
            platform_account_id="account",
            account_name="Account",
            token_expires_at=None,
            is_connected=False,
        )
    with pytest.raises(ValidationError):
        SubscriptionRead(
            id=uuid4(),
            organization_id=uuid4(),
            plan_name="Plan",
            amount=Decimal("-0.01"),
            currency="INR",
            status="pending",
        )
