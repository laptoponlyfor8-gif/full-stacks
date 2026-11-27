from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_user(session: AsyncSession, user_id: UUID) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def set_tenant_organization(
    session: AsyncSession,
    organization_id: UUID,
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )


@asynccontextmanager
async def tenant_transaction(
    session: AsyncSession,
    organization_id: UUID,
) -> AsyncIterator[AsyncSession]:
    if session.in_transaction():
        raise RuntimeError("Tenant context must be established before other database work.")

    async with session.begin():
        await set_tenant_organization(session, organization_id)
        yield session
