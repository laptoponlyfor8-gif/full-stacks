"""Add persistent authentication sessions and one-time auth tokens.

Revision ID: 20261107_0002
Revises: 20261107_0001
Create Date: 2026-11-07
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0002"
down_revision: str | None = "20261107_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mobile_number", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.execute(
        "CREATE TYPE auth_token_purpose AS ENUM "
        "('password_reset', 'email_verification')"
    )

    op.create_table(
        "auth_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_sessions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
    )
    op.create_index(
        "ix_auth_sessions_user_id",
        "auth_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_user_revoked",
        "auth_sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_created_at",
        "auth_sessions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("auth_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["auth_session_id"],
            ["auth_sessions.id"],
            name="fk_refresh_tokens_auth_session_id_auth_sessions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_replaced_by_id_refresh_tokens",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index(
        "ix_refresh_tokens_auth_session_id",
        "refresh_tokens",
        ["auth_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_user_revoked",
        "refresh_tokens",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_created_at",
        "refresh_tokens",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "auth_tokens",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "purpose",
            postgresql.ENUM(
                "password_reset",
                "email_verification",
                name="auth_token_purpose",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_tokens_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"], unique=False)
    op.create_index("ix_auth_tokens_purpose", "auth_tokens", ["purpose"], unique=False)
    op.create_index("ix_auth_tokens_created_at", "auth_tokens", ["created_at"], unique=False)

    op.execute("DROP POLICY tenant_isolation ON organizations")
    op.execute(
        "CREATE POLICY tenant_isolation ON organizations "
        "USING ("
        "id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
        "OR owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        ") WITH CHECK ("
        "id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
        "OR owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        ")"
    )
    op.execute("DROP POLICY tenant_isolation ON organization_members")
    op.execute(
        "CREATE POLICY tenant_isolation ON organization_members "
        "USING ("
        "organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
        "OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        ") WITH CHECK ("
        "organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
        "OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        ")"
    )
    for table in ("auth_sessions", "refresh_tokens", "auth_tokens"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY user_auth_isolation ON {table} "
            "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in ("auth_tokens", "refresh_tokens", "auth_sessions"):
        op.drop_table(table)
    op.execute("DROP TYPE auth_token_purpose")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "mobile_number")
    op.execute("DROP POLICY tenant_isolation ON organizations")
    op.execute(
        "CREATE POLICY tenant_isolation ON organizations "
        "USING (id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
        "WITH CHECK (id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)"
    )
    op.execute("DROP POLICY tenant_isolation ON organization_members")
    op.execute(
        "CREATE POLICY tenant_isolation ON organization_members "
        "USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)"
    )
