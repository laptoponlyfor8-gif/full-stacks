from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, require_organization_roles
from app.db.session import get_db_session
from app.models import OrganizationMember, User
from app.models.enums import OrganizationRole
from app.schemas.auth import MembershipResponse
from pydantic import BaseModel, ConfigDict, EmailStr

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationMemberView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    name: str
    email: EmailStr
    role: OrganizationRole


@router.get(
    "/{organization_id}/members",
    response_model=list[OrganizationMemberView],
)
async def list_organization_members(
    organization_id: UUID,
    _principal: Principal = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> list[OrganizationMemberView]:
    members = (
        await session.execute(
            select(
                OrganizationMember.user_id,
                User.name,
                User.email,
                OrganizationMember.role,
            )
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.created_at, OrganizationMember.id)
        )
    ).all()
    return [
        OrganizationMemberView(
            user_id=member.user_id,
            name=member.name,
            email=member.email,
            role=member.role,
        )
        for member in members
    ]


@router.get(
    "/{organization_id}/membership",
    response_model=MembershipResponse,
)
async def get_organization_membership(
    organization_id: UUID,
    principal: Principal = Depends(
        require_organization_roles(
            OrganizationRole.OWNER,
            OrganizationRole.ADMIN,
            OrganizationRole.MEMBER,
        )
    ),
) -> MembershipResponse:
    return MembershipResponse(
        organization_id=organization_id,
        role=principal.role.value,
    )
