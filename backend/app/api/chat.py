import json
import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.deps import Ctx, DBSession
from app.core.limiter import limiter
from app.models import ChatMessage, ChatSession
from app.schemas.chat import ChatRequest, ChatResponse, RetrievedChunk
from app.services import cache, feedback, llm, rag

log = structlog.get_logger()
router = APIRouter(prefix="/api/chat", tags=["chat"])


async def _ensure_session(db, ctx, session_id: int | None) -> ChatSession:
    s = await db.get(ChatSession, session_id) if session_id else None
    if not s:
        s = ChatSession(
            tenant_id=ctx.tenant_id, industry_code=ctx.industry_code,
            channel="debug", visitor_id=f"u{ctx.user_id}",
        )
        db.add(s); await db.commit(); await db.refresh(s)
    return s


async def _load_history(db, session_id: int, limit: int = 4) -> list[dict]:
    rows = (await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc()).limit(limit)
    )).scalars().all()
    return [{"role": m.role, "content": m.content[:300]} for m in reversed(rows)]


@router.post("", response_model=ChatResponse)
@limiter.limit("60/minute")
async def chat_endpoint(request: Request, req: ChatRequest, db: DBSession, ctx: Ctx):
    session = await _ensure_session(db, ctx, req.session_id)
    history = await _load_history(db, session.id)

    result = await rag.answer(
        db=db, ctx=ctx, question=req.question,
        top_k=req.top_k, knowledge_set_ids=req.knowledge_set_ids, history=history,
    )

    db.add(ChatMessage(
        session_id=session.id, tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code, role="user", content=req.question,
    ))
    db.add(ChatMessage(
        session_id=session.id, tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code, role="assistant", content=result["answer"],
        retrieval={
            "source": result.get("source"),
            "chunks": [{"chunk_id": c["chunk_id"], "score": c.get("score", 0)} for c in result["retrieval"]],
        },
    ))
    await db.commit()

    # Log low-confidence / unanswered for ops to review
    await feedback.log_if_needed(
        db, ctx,
        question=req.question, answer=result["answer"],
        confidence=result["confidence"], source=result.get("source", "llm"),
        n_chunks=len(result["retrieval"]),
        chunk_summaries=[
            {"chunk_id": c["chunk_id"], "document_title": c.get("document_title", ""),
             "score": c.get("score", 0)}
            for c in result["retrieval"][:5]
        ],
        session_id=session.id,
        thresholds=result.get("thresholds"),
    )

    return ChatResponse(
        session_id=session.id,
        answer=result["answer"],
        retrieval=[RetrievedChunk(**{
            "chunk_id": c["chunk_id"], "document_id": c["document_id"],
            "document_title": c.get("document_title", ""),
            "score": c.get("rerank_score", c.get("score", 0)), "text": c["text"],
        }) for c in result["retrieval"]],
        confidence=result["confidence"],
        suggest_handoff=result["suggest_handoff"],
        debug={
            "source": result.get("source"),
            "faq_hit": result.get("faq_hit"),
            "cache_hit": result.get("cache_hit"),
            "retrieval_debug": result.get("debug"),
        } if req.debug else None,
    )


@router.post("/stream")
@limiter.limit("60/minute")
async def chat_stream_endpoint(request: Request, req: ChatRequest, db: DBSession, ctx: Ctx):
    """SSE stream:
       event: meta   data: {session_id, retrieval, confidence, source, faq_hit, cache_hit, debug}
       event: delta  data: {text}
       event: done   data: {}
    """
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    def mark(n): timings[n] = round((time.perf_counter() - t0) * 1000, 1)

    session = await _ensure_session(db, ctx, req.session_id)
    mark("session_ready")
    history = await _load_history(db, session.id)
    mark("history_loaded")

    thresholds = await feedback.get_industry_thresholds(db, ctx.industry_code)

    # Cache lookup first
    cached = await cache.lookup(ctx.tenant_id, ctx.industry_code, req.question)
    mark("cache_lookup")

    if cached:
        chunks_for_meta: list[dict] = []
        retrieval_debug = None
        faq_hit = None
        source = "cache"
        answer_static = cached["answer"]
    else:
        # Retrieve
        r = await rag.retrieve(db, ctx, req.question, top_k=req.top_k,
                                knowledge_set_ids=req.knowledge_set_ids)
        chunks_for_meta = r["chunks"]
        retrieval_debug = r["debug"]
        faq_hit = r["faq_hit"]
        mark("retrieved")

        if faq_hit:
            source = "faq"
            answer_static = faq_hit["answer"]
        elif not chunks_for_meta:
            source = "fallback"
            answer_static = ("您能再描述得详细一些吗？我帮您查一下，或者您可以告诉我具体要了解的方面。"
                             if thresholds["soft_mode"]
                             else "抱歉，我暂时没有相关信息，建议您联系人工客服。")
        else:
            source = "llm"
            answer_static = None  # will stream

    # persist user msg now
    db.add(ChatMessage(
        session_id=session.id, tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code, role="user", content=req.question,
    ))
    await db.commit()
    mark("user_msg_saved")

    session_id = session.id
    top_score = (chunks_for_meta[0].get("rerank_score", chunks_for_meta[0].get("score", 0))
                 if chunks_for_meta else (cached["score"] if cached else 0.0))
    if cached or faq_hit:
        suggest_handoff = False
    elif not chunks_for_meta:
        suggest_handoff = not thresholds["soft_mode"]
    else:
        suggest_handoff = top_score < thresholds["handoff_threshold"]

    async def event_gen():
        yield ": ping\n\n"
        meta = {
            "session_id": session_id,
            "source": source,
            "retrieval": [
                {"chunk_id": c["chunk_id"], "document_id": c["document_id"],
                 "document_title": c.get("document_title", ""),
                 "score": c.get("rerank_score", c.get("score", 0)), "text": c["text"]}
                for c in chunks_for_meta
            ],
            "confidence": top_score,
            "suggest_handoff": suggest_handoff,
            "faq_hit": faq_hit,
            "cache_hit": cached,
            "retrieval_debug": retrieval_debug,
            "timings_ms": timings,
        }
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

        if answer_static is not None:
            # Send the static answer in one delta (or chunked for nicer UX)
            yield f"event: delta\ndata: {json.dumps({'text': answer_static}, ensure_ascii=False)}\n\n"
            buf = answer_static
        else:
            contexts = [c["text"][:500] for c in chunks_for_meta]
            msgs = llm.build_messages(req.question, contexts, history=history)
            buf_parts: list[str] = []
            first = True
            async for delta in llm.chat_stream(msgs):
                if first:
                    mark("llm_first_token")
                    log.info("chat.timings", source=source, **timings)
                    first = False
                buf_parts.append(delta)
                yield f"event: delta\ndata: {json.dumps({'text': delta}, ensure_ascii=False)}\n\n"
            buf = "".join(buf_parts)
            # apply soft hedge to LLM answers
            hedged = feedback.maybe_add_hedge(buf, top_score, thresholds)
            if hedged != buf:
                tail = hedged[len(buf):]
                yield f"event: delta\ndata: {json.dumps({'text': tail}, ensure_ascii=False)}\n\n"
                buf = hedged
            mark("llm_done")

        # Persist assistant msg + cache + log low-confidence in a fresh DB session
        from app.core.db import SessionLocal
        async with SessionLocal() as s2:
            s2.add(ChatMessage(
                session_id=session_id, tenant_id=ctx.tenant_id,
                industry_code=ctx.industry_code, role="assistant", content=buf,
                retrieval={
                    "source": source,
                    "chunks": [{"chunk_id": c["chunk_id"]} for c in chunks_for_meta],
                },
            ))
            await s2.commit()
            await feedback.log_if_needed(
                s2, ctx,
                question=req.question, answer=buf,
                confidence=top_score, source=source,
                n_chunks=len(chunks_for_meta),
                chunk_summaries=[
                    {"chunk_id": c["chunk_id"], "document_title": c.get("document_title", ""),
                     "score": c.get("score", 0)}
                    for c in chunks_for_meta[:5]
                ],
                session_id=session_id, thresholds=thresholds,
            )
        if not cached and buf and source != "fallback":
            await cache.store(ctx.tenant_id, ctx.industry_code, req.question, buf)

        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@router.delete("/cache")
async def clear_cache(ctx: Ctx):
    n = await cache.clear(ctx.tenant_id, ctx.industry_code)
    return {"cleared": n}
