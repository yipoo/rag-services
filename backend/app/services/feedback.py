"""Record low-confidence / unanswered chats for ops to review and convert into FAQs."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestContext
from app.models import Industry, UnansweredQuestion


async def get_industry_thresholds(db: AsyncSession, industry_code: str) -> dict:
    ind = (await db.execute(select(Industry).where(Industry.code == industry_code))).scalar_one_or_none()
    if not ind:
        return {"handoff_threshold": 0.3, "record_threshold": 0.7, "soft_mode": True}
    return {
        "handoff_threshold": ind.handoff_threshold,
        "record_threshold": ind.record_threshold,
        "soft_mode": ind.soft_mode,
    }


def categorize(confidence: float, n_chunks: int, thresholds: dict) -> str | None:
    """Return category if should be recorded; None if confidence is high enough."""
    if n_chunks == 0:
        return "miss"
    if confidence < thresholds["handoff_threshold"]:
        return "handoff"
    if confidence < thresholds["record_threshold"]:
        return "low"
    return None


async def log_if_needed(
    db: AsyncSession,
    ctx: RequestContext,
    *,
    question: str,
    answer: str,
    confidence: float,
    source: str,
    n_chunks: int,
    chunk_summaries: list[dict] | None = None,
    session_id: int | None = None,
    thresholds: dict | None = None,
) -> bool:
    """Returns True if a record was created."""
    if thresholds is None:
        thresholds = await get_industry_thresholds(db, ctx.industry_code)
    cat = categorize(confidence, n_chunks, thresholds)
    if cat is None:
        return False
    rec = UnansweredQuestion(
        tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code,
        session_id=session_id,
        question=question[:2000],
        answer_given=(answer or "")[:2000],
        confidence=float(confidence or 0),
        source=source,
        category=cat,
        retrieval={"chunks": chunk_summaries or []},
    )
    db.add(rec)
    await db.commit()
    return True


SOFT_HEDGE = "\n\n（如需更详细的信息，欢迎进一步描述您的问题，或留言由人工跟进。）"


def maybe_add_hedge(answer: str, confidence: float, thresholds: dict) -> str:
    """In soft_mode, append a gentle disclaimer if confidence is borderline."""
    if not thresholds.get("soft_mode"):
        return answer
    # Only hedge in the "low" zone (between handoff and record). Skip if very high or already a hand-off line.
    if thresholds["handoff_threshold"] <= confidence < thresholds["record_threshold"]:
        if not answer.endswith(("人工", "客服", "联系", "跟进。）")):
            return answer + SOFT_HEDGE
    return answer
