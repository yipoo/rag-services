"""Platform-admin endpoints: tenant CRUD, subscriptions, member mgmt."""
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.core.security import hash_password
from app.models import Tenant, TenantIndustrySubscription, TenantMember, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user: User):
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin only")


class TenantCreate(BaseModel):
    code: str
    name: str
    plan: str = "basic"
    default_industry_code: str | None = None
    industries: list[str] = []
    admin_email: EmailStr
    admin_password: str
    admin_name: str = ""


class TenantOut(BaseModel):
    id: int
    code: str
    name: str
    plan: str
    default_industry_code: str | None
    industries: list[str]


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(user: CurrentUser, db: DBSession):
    _require_admin(user)
    tenants = (await db.execute(select(Tenant).order_by(Tenant.id))).scalars().all()
    out = []
    for t in tenants:
        subs = (await db.execute(
            select(TenantIndustrySubscription).where(TenantIndustrySubscription.tenant_id == t.id)
        )).scalars().all()
        out.append(TenantOut(
            id=t.id, code=t.code, name=t.name, plan=t.plan,
            default_industry_code=t.default_industry_code,
            industries=[s.industry_code for s in subs],
        ))
    return out


@router.post("/tenants", response_model=TenantOut)
async def create_tenant(req: TenantCreate, user: CurrentUser, db: DBSession):
    _require_admin(user)
    exists = (await db.execute(select(Tenant).where(Tenant.code == req.code))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tenant code exists")

    t = Tenant(code=req.code, name=req.name, plan=req.plan, default_industry_code=req.default_industry_code)
    db.add(t)
    await db.flush()

    for code in req.industries:
        db.add(TenantIndustrySubscription(tenant_id=t.id, industry_code=code))

    # create or attach admin user
    u = (await db.execute(select(User).where(User.email == req.admin_email))).scalar_one_or_none()
    if not u:
        u = User(email=req.admin_email, hashed_password=hash_password(req.admin_password),
                name=req.admin_name or req.admin_email.split("@")[0])
        db.add(u)
        await db.flush()
    db.add(TenantMember(tenant_id=t.id, user_id=u.id, role="admin"))

    await db.commit()
    await db.refresh(t)
    return TenantOut(
        id=t.id, code=t.code, name=t.name, plan=t.plan,
        default_industry_code=t.default_industry_code, industries=req.industries,
    )


class SubscriptionUpdate(BaseModel):
    industries: list[str]


@router.put("/tenants/{tenant_id}/subscriptions", response_model=TenantOut)
async def update_subscriptions(tenant_id: int, req: SubscriptionUpdate, user: CurrentUser, db: DBSession):
    _require_admin(user)
    t = await db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    existing = (await db.execute(
        select(TenantIndustrySubscription).where(TenantIndustrySubscription.tenant_id == tenant_id)
    )).scalars().all()
    for s in existing:
        await db.delete(s)
    await db.flush()
    for code in req.industries:
        db.add(TenantIndustrySubscription(tenant_id=tenant_id, industry_code=code))
    await db.commit()
    return TenantOut(id=t.id, code=t.code, name=t.name, plan=t.plan,
                     default_industry_code=t.default_industry_code, industries=req.industries)
