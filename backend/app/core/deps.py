from typing import Annotated, AsyncIterator

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.core.db import SessionLocal
from app.core.security import decode_token
from app.models import Tenant, TenantMember, User, TenantIndustrySubscription


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DBSession,
) -> User:
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_request_context(
    user: CurrentUser,
    db: DBSession,
    x_tenant_id: Annotated[int | None, Header(alias="X-Tenant-Id")] = None,
    x_industry: Annotated[str | None, Header(alias="X-Industry")] = None,
) -> RequestContext:
    """Build per-request multi-tenant context.

    Resolves tenant_id from X-Tenant-Id header; verifies the user is a member.
    Resolves industry_code from X-Industry header or tenant default.
    """

    # Platform admin can act on any tenant; if header missing, treat as PLATFORM (0)
    if user.is_platform_admin:
        tenant_id = x_tenant_id if x_tenant_id is not None else 0
        role = "platform_admin"
    else:
        if x_tenant_id is None:
            # auto-pick the user's first tenant
            res = await db.execute(
                select(TenantMember).where(TenantMember.user_id == user.id).limit(1)
            )
            member = res.scalar_one_or_none()
            if not member:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no tenant")
            tenant_id = member.tenant_id
            role = member.role
        else:
            res = await db.execute(
                select(TenantMember).where(
                    TenantMember.user_id == user.id, TenantMember.tenant_id == x_tenant_id
                )
            )
            member = res.scalar_one_or_none()
            if not member:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this tenant")
            tenant_id = x_tenant_id
            role = member.role

    # Resolve industry
    industry_code = x_industry
    if not industry_code and tenant_id > 0:
        tenant = await db.get(Tenant, tenant_id)
        if tenant:
            industry_code = tenant.default_industry_code
    if not industry_code:
        industry_code = "general"

    # Resolve retrieval scope: this industry only (subscription check informational)
    industry_codes = [industry_code]

    return RequestContext(
        user_id=user.id,
        tenant_id=tenant_id,
        industry_code=industry_code,
        industry_codes=industry_codes,
        is_platform_admin=user.is_platform_admin,
        role=role,
    )


Ctx = Annotated[RequestContext, Depends(get_request_context)]


def require_role(*roles: str):
    async def checker(ctx: Ctx) -> RequestContext:
        if ctx.is_platform_admin:
            return ctx
        if ctx.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return ctx
    return checker
