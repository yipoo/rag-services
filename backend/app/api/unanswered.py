from datetime import datetime

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.deps import Ctx, DBSession
from app.models import FAQ, UnansweredQuestion
from app.services import faq as faq_svc

router = APIRouter(prefix="/api/unanswered", tags=["unanswered"])


class UnansweredOut(BaseModel):
    id: int
    question: str
    answer_given: str
    confidence: float
    source: str
    category: str
    status: str
    handled_faq_id: int | None
    retrieval: dict
    session_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[UnansweredOut])
async def list_unanswered(
    db: DBSession, ctx: Ctx,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    stmt = select(UnansweredQuestion).where(
        UnansweredQuestion.tenant_id == ctx.tenant_id,
        UnansweredQuestion.industry_code == ctx.industry_code,
    )
    if status_filter:
        stmt = stmt.where(UnansweredQuestion.status == status_filter)
    if category:
        stmt = stmt.where(UnansweredQuestion.category == category)
    if q:
        stmt = stmt.where(UnansweredQuestion.question.ilike(f"%{q}%"))
    stmt = stmt.order_by(UnansweredQuestion.id.desc()).limit(limit).offset(offset)
    return (await db.execute(stmt)).scalars().all()


@router.get("/stats")
async def stats(db: DBSession, ctx: Ctx):
    """Counts grouped by status and category."""
    base = select(UnansweredQuestion).where(
        UnansweredQuestion.tenant_id == ctx.tenant_id,
        UnansweredQuestion.industry_code == ctx.industry_code,
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    by_status_q = (await db.execute(
        select(UnansweredQuestion.status, func.count()).select_from(UnansweredQuestion).where(
            UnansweredQuestion.tenant_id == ctx.tenant_id,
            UnansweredQuestion.industry_code == ctx.industry_code,
        ).group_by(UnansweredQuestion.status)
    )).all()
    by_category_q = (await db.execute(
        select(UnansweredQuestion.category, func.count()).select_from(UnansweredQuestion).where(
            UnansweredQuestion.tenant_id == ctx.tenant_id,
            UnansweredQuestion.industry_code == ctx.industry_code,
        ).group_by(UnansweredQuestion.category)
    )).all()
    return {
        "total": total,
        "by_status": {k: v for k, v in by_status_q},
        "by_category": {k: v for k, v in by_category_q},
    }


class StatusUpdate(BaseModel):
    status: str  # pending / handled / dismissed


@router.patch("/{uid}", response_model=UnansweredOut)
async def update_status(uid: int, req: StatusUpdate, db: DBSession, ctx: Ctx):
    u = await db.get(UnansweredQuestion, uid)
    if not u or u.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if req.status not in ("pending", "handled", "dismissed"):
        raise HTTPException(400, "invalid status")
    u.status = req.status
    await db.commit(); await db.refresh(u)
    return u


@router.delete("/{uid}")
async def delete_unanswered(uid: int, db: DBSession, ctx: Ctx):
    u = await db.get(UnansweredQuestion, uid)
    if not u or u.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await db.delete(u); await db.commit()
    return {"ok": True}


class ConvertReq(BaseModel):
    question: str | None = None    # override standard question (default: original)
    answer: str                    # required
    similar_questions: list[str] = []
    knowledge_set_id: int | None = None
    mark_handled: bool = True


@router.post("/{uid}/convert-to-faq", response_model=UnansweredOut)
async def convert_to_faq(uid: int, req: ConvertReq, db: DBSession, ctx: Ctx):
    u = await db.get(UnansweredQuestion, uid)
    if not u or u.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # Use the original question as a similar question to broaden recall
    sims = list(req.similar_questions)
    if u.question and u.question != (req.question or u.question):
        sims.append(u.question)

    f = FAQ(
        tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code,
        scope="PUBLIC" if ctx.tenant_id == 0 else "PRIVATE",
        knowledge_set_id=req.knowledge_set_id,
        question=(req.question or u.question).strip(),
        answer=req.answer.strip(),
        similar_questions=[s.strip() for s in sims if s.strip()],
    )
    db.add(f); await db.flush()
    await faq_svc.reindex(db, f)

    u.handled_faq_id = f.id
    if req.mark_handled:
        u.status = "handled"
    await db.commit(); await db.refresh(u)
    return u
