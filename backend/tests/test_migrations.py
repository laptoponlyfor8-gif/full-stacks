from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


def test_initial_migration_generates_postgresql_schema_sql(monkeypatch) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    output = StringIO()
    config.output_buffer = output
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://migration_test@localhost:5432/migration_test",
    )
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    try:
        command.upgrade(config, "head", sql=True)
    finally:
        get_settings.cache_clear()

    sql = output.getvalue()
    for table in (
        "users",
        "organizations",
        "organization_members",
        "social_accounts",
        "automations",
        "automation_keywords",
        "messages",
        "subscriptions",
        "billing_plans",
        "billing_customers",
        "payments",
        "billing_webhook_events",
        "billing_event_logs",
        "auth_sessions",
        "refresh_tokens",
        "auth_tokens",
        "meta_webhook_account_routes",
        "webhook_events",
        "automation_executions",
        "message_delivery_attempts",
        "ai_provider_configurations",
        "ai_conversations",
        "ai_messages",
        "business_knowledge",
        "ai_usage_records",
        "contacts",
        "contact_notes",
        "contact_tags",
        "contact_tag_assignments",
        "lead_activities",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "CREATE POLICY tenant_isolation" in sql
    assert sql.count("CREATE POLICY tenant_isolation") == 26
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "fk_automations_org_account" in sql
    assert "uq_members_org_user" in sql
    assert "auth_version" in sql
    assert "CREATE POLICY user_auth_isolation" in sql
    assert "grace_period_ends_at" in sql
    assert "provider_event_at" in sql
