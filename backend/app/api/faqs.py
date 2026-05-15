import csv
import io

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.deps import Ctx, DBSession
from app.models import FAQ
from app.schemas.knowledge import FAQCreate, FAQOut
from app.core.config import settings
from app.services import faq as faq_svc
from app.services import file_guard

router = APIRouter(prefix="/api/faqs", tags=["faqs"])


@router.get("", response_model=list[FAQOut])
async def list_faqs(db: DBSession, ctx: Ctx, knowledge_set_id: int | None = None,
                    q: str | None = None, limit: int = 200, offset: int = 0):
    stmt = select(FAQ).where(FAQ.tenant_id == ctx.tenant_id, FAQ.industry_code == ctx.industry_code)
    if knowledge_set_id is not None:
        stmt = stmt.where(FAQ.knowledge_set_id == knowledge_set_id)
    if q:
        stmt = stmt.where(FAQ.question.ilike(f"%{q}%"))
    stmt = stmt.order_by(FAQ.id.desc()).limit(limit).offset(offset)
    return (await db.execute(stmt)).scalars().all()


@router.post("", response_model=FAQOut)
async def create_faq(req: FAQCreate, db: DBSession, ctx: Ctx):
    f = FAQ(
        tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code,
        scope="PUBLIC" if ctx.tenant_id == 0 else "PRIVATE",
        knowledge_set_id=req.knowledge_set_id,
        question=req.question.strip(),
        answer=req.answer.strip(),
        similar_questions=[s.strip() for s in (req.similar_questions or []) if s.strip()],
    )
    db.add(f); await db.commit(); await db.refresh(f)
    await faq_svc.reindex(db, f)
    return f


class FAQUpdate(FAQCreate):
    is_active: bool | None = None


@router.patch("/{faq_id}", response_model=FAQOut)
async def update_faq(faq_id: int, req: FAQUpdate, db: DBSession, ctx: Ctx):
    f = await db.get(FAQ, faq_id)
    if not f or f.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FAQ not found")
    f.question = req.question.strip()
    f.answer = req.answer.strip()
    f.similar_questions = [s.strip() for s in (req.similar_questions or []) if s.strip()]
    if req.knowledge_set_id is not None:
        f.knowledge_set_id = req.knowledge_set_id
    if req.is_active is not None:
        f.is_active = req.is_active
    await db.commit()
    await faq_svc.reindex(db, f)
    await db.refresh(f)
    return f


@router.delete("/{faq_id}")
async def delete_faq(faq_id: int, db: DBSession, ctx: Ctx):
    f = await db.get(FAQ, faq_id)
    if not f or f.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FAQ not found")
    faq_svc.remove(f)
    await db.delete(f); await db.commit()
    return {"ok": True}


@router.post("/import")
async def import_csv(db: DBSession, ctx: Ctx, file: UploadFile = File(...),
                     knowledge_set_id: int | None = None):
    """CSV columns: question, answer, similar_questions(|-separated, optional)"""
    try:
        # cap file size
        raw_bytes = await file.read(settings.MAX_UPLOAD_BYTES + 1)
        file_guard.check_bytes(raw_bytes, label="CSV")
    except file_guard.UnsafeFileError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    raw = raw_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    created = 0
    for i, row in enumerate(reader):
        if i >= settings.MAX_CSV_ROWS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"CSV exceeds max rows ({settings.MAX_CSV_ROWS})"
            )
        q = (row.get("question") or "").strip()[:2000]
        a = (row.get("answer") or "").strip()[:5000]
        if not q or not a:
            continue
        sims_raw = (row.get("similar_questions") or "").strip()
        sims = [s.strip()[:500] for s in sims_raw.split("|") if s.strip()][:20] if sims_raw else []
        f = FAQ(
            tenant_id=ctx.tenant_id, industry_code=ctx.industry_code,
            scope="PUBLIC" if ctx.tenant_id == 0 else "PRIVATE",
            knowledge_set_id=knowledge_set_id,
            question=q, answer=a, similar_questions=sims,
        )
        db.add(f); await db.flush()
        await faq_svc.reindex(db, f)
        created += 1
    await db.commit()
    return {"imported": created}


@router.get("/export.csv")
async def export_csv(db: DBSession, ctx: Ctx):
    rows = (await db.execute(
        select(FAQ).where(FAQ.tenant_id == ctx.tenant_id, FAQ.industry_code == ctx.industry_code)
    )).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["question", "answer", "similar_questions"])
    for f in rows:
        w.writerow([f.question, f.answer, "|".join(f.similar_questions or [])])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="faqs_{ctx.industry_code}.csv"'},
    )
