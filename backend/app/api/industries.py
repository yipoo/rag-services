from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession, Ctx
from app.models import Industry
from app.schemas.industry import IndustryCreate, IndustryOut, IndustryUpdate

router = APIRouter(prefix="/api/industries", tags=["industries"])


@router.get("", response_model=list[IndustryOut])
async def list_industries(db: DBSession, ctx: Ctx):
    rows = (await db.execute(select(Industry).where(Industry.is_active == True).order_by(Industry.id))).scalars().all()
    return rows


@router.post("", response_model=IndustryOut)
async def create_industry(req: IndustryCreate, db: DBSession, user: CurrentUser):
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only platform admin can create industries")
    exists = (await db.execute(select(Industry).where(Industry.code == req.code))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Industry code already exists")
    obj = Industry(**req.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/{code}", response_model=IndustryOut)
async def update_industry(code: str, req: IndustryUpdate, db: DBSession, user: CurrentUser):
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only platform admin can update industries")
    obj = (await db.execute(select(Industry).where(Industry.code == code))).scalar_one_or_none()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Industry not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj
