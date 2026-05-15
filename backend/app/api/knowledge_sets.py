from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import Ctx, DBSession
from app.models import KnowledgeSet
from app.schemas.knowledge import KnowledgeSetCreate, KnowledgeSetOut, KnowledgeSetUpdate

router = APIRouter(prefix="/api/knowledge-sets", tags=["knowledge-sets"])


@router.get("", response_model=list[KnowledgeSetOut])
async def list_sets(db: DBSession, ctx: Ctx):
    rows = (await db.execute(
        select(KnowledgeSet).where(
            KnowledgeSet.tenant_id == ctx.tenant_id,
            KnowledgeSet.industry_code == ctx.industry_code,
        ).order_by(KnowledgeSet.id)
    )).scalars().all()
    return rows


@router.post("", response_model=KnowledgeSetOut)
async def create_set(req: KnowledgeSetCreate, db: DBSession, ctx: Ctx):
    obj = KnowledgeSet(
        tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code,
        scope="PUBLIC" if ctx.tenant_id == 0 else "PRIVATE",
        name=req.name,
        description=req.description,
        weight=req.weight,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/{set_id}", response_model=KnowledgeSetOut)
async def update_set(set_id: int, req: KnowledgeSetUpdate, db: DBSession, ctx: Ctx):
    obj = await db.get(KnowledgeSet, set_id)
    if not obj or obj.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge set not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{set_id}")
async def delete_set(set_id: int, db: DBSession, ctx: Ctx):
    obj = await db.get(KnowledgeSet, set_id)
    if not obj or obj.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge set not found")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}
