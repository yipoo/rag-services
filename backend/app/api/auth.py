from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.core.limiter import limiter
from app.core.security import create_access_token, verify_password
from app.models import Tenant, TenantIndustrySubscription, TenantMember, User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, TenantBrief

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest, db: DBSession):
    user = (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User inactive")
    token = create_access_token(str(user.id))
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=user.name,
        is_platform_admin=user.is_platform_admin,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, db: DBSession):
    members = (
        await db.execute(select(TenantMember).where(TenantMember.user_id == user.id))
    ).scalars().all()

    tenants_out: list[TenantBrief] = []
    for m in members:
        t = await db.get(Tenant, m.tenant_id)
        if not t:
            continue
        subs = (
            await db.execute(
                select(TenantIndustrySubscription).where(TenantIndustrySubscription.tenant_id == t.id)
            )
        ).scalars().all()
        tenants_out.append(TenantBrief(
            id=t.id,
            code=t.code,
            name=t.name,
            role=m.role,
            default_industry_code=t.default_industry_code,
            industries=[s.industry_code for s in subs],
        ))

    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenants_out,
    )
