"""Hybrid retriever with multiple stages and full debug visibility.

Pipeline:
  1) FAQ vector search   — if top_score >= FAQ_HIT_THRESHOLD: short-circuit (return canned answer)
  2) Vector search (chunks)
  3) BM25 search (chunks)
  4) RRF fusion
  5) Rerank (cross-encoder, optional)
"""
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import RequestContext
from app.models import FAQ, Chunk, Document
from app.services import bm25, embeddings, reranker, vector_store


@dataclass
class RetrievalDebug:
    timings: dict[str, float] = field(default_factory=dict)
    stages: dict[str, list[dict]] = field(default_factory=dict)
    short_circuit: bool = False
    faq_hit: dict | None = None


def _rrf_merge(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal-rank fusion. rankings = [[id ranked desc by relevance], ...]"""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


async def hybrid_retrieve(
    db: AsyncSession,
    ctx: RequestContext,
    question: str,
    top_k: int = 5,
    knowledge_set_ids: list[int] | None = None,
    enable_faq_short_circuit: bool = True,
    enable_rerank: bool = True,
) -> tuple[list[dict], RetrievalDebug | None, dict | None]:
    """Returns (final_chunks, debug, faq_short_circuit_or_None).
       If FAQ short-circuit hits, faq_short_circuit_or_None is the FAQ dict; final_chunks are still
       the supporting context for transparency.
    """
    dbg = RetrievalDebug()
    t = time.perf_counter()

    def mark(name):
        dbg.timings[name] = round((time.perf_counter() - t) * 1000, 1)

    # --- 1) Embed query (used by FAQ + vector search; reuse) ---
    qvec = embeddings.embed_one(question)
    mark("embed")

    # --- 2) FAQ short-circuit ---
    faq_short_circuit = None
    if enable_faq_short_circuit:
        faq_hits = vector_store.search(
            vector=qvec,
            tenant_id=ctx.tenant_id,
            industry_codes=ctx.industry_codes,
            top_k=3,
            knowledge_set_ids=knowledge_set_ids,
            kind="faq",
        )
        mark("faq_search")
        dbg.stages["faq"] = [
            {"score": h["score"], "faq_id": h["payload"].get("faq_id"),
             "text": h["payload"].get("text", "")}
            for h in faq_hits
        ]
        if faq_hits and faq_hits[0]["score"] >= settings.FAQ_HIT_THRESHOLD:
            top = faq_hits[0]
            faq = await db.get(FAQ, top["payload"].get("faq_id"))
            if faq and faq.is_active:
                faq.hit_count = (faq.hit_count or 0) + 1
                await db.commit()
                faq_short_circuit = {
                    "faq_id": faq.id,
                    "question": faq.question,
                    "answer": faq.answer,
                    "score": top["score"],
                }
                dbg.short_circuit = True
                dbg.faq_hit = faq_short_circuit

    # --- 3) Vector search over chunks ---
    vec_hits = vector_store.search(
        vector=qvec,
        tenant_id=ctx.tenant_id,
        industry_codes=ctx.industry_codes,
        top_k=settings.HYBRID_VECTOR_TOP_K,
        knowledge_set_ids=knowledge_set_ids,
        kind="chunk",
    )
    mark("vector_search")
    vec_ranking = [h["payload"].get("chunk_id") for h in vec_hits if h["payload"].get("chunk_id")]
    dbg.stages["vector"] = [
        {"chunk_id": h["payload"].get("chunk_id"), "score": h["score"]}
        for h in vec_hits
    ]

    # --- 4) BM25 search ---
    bm25_hits = await bm25.search(
        db=db, tenant_id=ctx.tenant_id, industry_codes=ctx.industry_codes,
        query=question, top_k=settings.HYBRID_BM25_TOP_K,
    )
    mark("bm25_search")
    bm25_ranking = [h["chunk_id"] for h in bm25_hits]
    dbg.stages["bm25"] = bm25_hits

    # --- 5) RRF fusion ---
    fused = _rrf_merge([vec_ranking, bm25_ranking], k=settings.HYBRID_RRF_K)
    mark("rrf")
    fused_sorted = sorted(fused.items(), key=lambda kv: -kv[1])[: max(top_k * 4, 10)]
    candidate_ids = [cid for cid, _ in fused_sorted]
    if not candidate_ids:
        return [], dbg, faq_short_circuit

    # Hydrate from DB (text + doc title)
    rows = (await db.execute(
        select(Chunk, Document.title).join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_(candidate_ids))
    )).all()
    by_id = {c.id: (c, title) for c, title in rows}
    candidates: list[dict] = []
    for cid, fscore in fused_sorted:
        if cid not in by_id:
            continue
        c, title = by_id[cid]
        candidates.append({
            "chunk_id": c.id,
            "document_id": c.document_id,
            "document_title": title,
            "score": fscore,
            "text": c.text,
        })
    dbg.stages["fused"] = [
        {"chunk_id": x["chunk_id"], "score": x["score"]} for x in candidates
    ]

    # --- 6) Rerank ---
    final = candidates
    if enable_rerank and candidates:
        final = reranker.rerank(question, candidates, top_k=settings.RERANK_TOP_K)
        mark("rerank")
        dbg.stages["reranked"] = [
            {"chunk_id": x["chunk_id"], "rerank_score": x.get("rerank_score", 0)} for x in final
        ]

    final = final[:top_k]
    return final, dbg, faq_short_circuit
