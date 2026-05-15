"""RAG orchestration: hybrid retrieve -> FAQ shortcut -> semantic cache -> LLM."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import RequestContext
from app.services import cache, feedback, llm, retriever


async def retrieve(
    db: AsyncSession,
    ctx: RequestContext,
    question: str,
    top_k: int = 5,
    knowledge_set_ids: list[int] | None = None,
    enable_faq_short_circuit: bool = True,
    enable_rerank: bool = True,
) -> dict:
    """Pure retrieval (no LLM). Returns {chunks, debug, faq_hit}."""
    chunks, dbg, faq = await retriever.hybrid_retrieve(
        db=db, ctx=ctx, question=question, top_k=top_k,
        knowledge_set_ids=knowledge_set_ids,
        enable_faq_short_circuit=enable_faq_short_circuit,
        enable_rerank=enable_rerank,
    )
    return {
        "chunks": chunks,
        "debug": {
            "timings_ms": dbg.timings,
            "stages": dbg.stages,
            "short_circuit": dbg.short_circuit,
        } if dbg else None,
        "faq_hit": faq,
    }


async def answer(
    db: AsyncSession,
    ctx: RequestContext,
    question: str,
    top_k: int = 5,
    knowledge_set_ids: list[int] | None = None,
    history: list[dict] | None = None,
) -> dict:
    """Full pipeline with soft-mode + low-confidence logging.
    cache -> retrieve -> (FAQ | LLM | soft fallback) -> hedge -> log
    """
    thresholds = await feedback.get_industry_thresholds(db, ctx.industry_code)

    # 1. Semantic cache
    cached = await cache.lookup(ctx.tenant_id, ctx.industry_code, question)
    if cached:
        return {
            "answer": cached["answer"],
            "retrieval": [],
            "confidence": cached["score"],
            "suggest_handoff": False,
            "source": "cache",
            "cache_hit": cached,
            "thresholds": thresholds,
        }

    # 2. Retrieve
    r = await retrieve(db, ctx, question, top_k=top_k,
                       knowledge_set_ids=knowledge_set_ids)
    chunks = r["chunks"]
    faq = r["faq_hit"]

    # 3. FAQ short-circuit
    if faq:
        await cache.store(ctx.tenant_id, ctx.industry_code, question, faq["answer"])
        return {
            "answer": faq["answer"],
            "retrieval": chunks,
            "confidence": faq["score"],
            "suggest_handoff": False,
            "source": "faq",
            "faq_hit": faq,
            "debug": r["debug"],
            "thresholds": thresholds,
        }

    # 4. Empty retrieval — in soft mode, ask the user to elaborate; otherwise refuse
    if not chunks:
        if thresholds["soft_mode"]:
            text = "您能再描述得详细一些吗？我帮您查一下，或者您可以告诉我具体要了解的方面。"
        else:
            text = "抱歉，我暂时没有相关信息，建议您联系人工客服。"
        return {
            "answer": text,
            "retrieval": [],
            "confidence": 0.0,
            "suggest_handoff": not thresholds["soft_mode"],
            "source": "fallback",
            "debug": r["debug"],
            "thresholds": thresholds,
        }

    # 5. LLM
    contexts = [c["text"][:500] for c in chunks]
    top_score = chunks[0].get("rerank_score", chunks[0].get("score", 0.0))
    msgs = llm.build_messages(question, contexts, history=history)
    text = await llm.chat(msgs)
    text = feedback.maybe_add_hedge(text, top_score, thresholds)

    # 6. Cache
    await cache.store(ctx.tenant_id, ctx.industry_code, question, text)

    return {
        "answer": text,
        "retrieval": chunks,
        "confidence": top_score,
        "suggest_handoff": top_score < thresholds["handoff_threshold"],
        "source": "llm",
        "debug": r["debug"],
        "thresholds": thresholds,
    }
