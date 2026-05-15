"""BM25 lexical retrieval over chunks. Uses jieba for Chinese tokenization,
rank_bm25 for scoring. Per (tenant_id, industry_code) in-memory index with TTL cache.

For MVP scale (≤ ~100k chunks per tenant) this is plenty fast and zero-deps on PG extensions.
"""
import threading
from dataclasses import dataclass

import jieba
import structlog
from cachetools import TTLCache
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk

log = structlog.get_logger()

# Suppress jieba's INFO log
jieba.setLogLevel(40)

# (tenant_id, industry_code) -> _Index ; ttl 5 min
_cache: TTLCache = TTLCache(maxsize=256, ttl=300)
_lock = threading.Lock()


@dataclass
class _Index:
    bm25: BM25Okapi
    chunk_ids: list[int]


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t for t in jieba.cut_for_search(text) if t.strip()]


def _key(tenant_id: int, industry_code: str) -> tuple[int, str]:
    return (tenant_id, industry_code)


def invalidate(tenant_id: int, industry_code: str) -> None:
    """Drop the BM25 index for a (tenant, industry). Called on chunk write/delete."""
    with _lock:
        _cache.pop(_key(tenant_id, industry_code), None)


async def _build(db: AsyncSession, tenant_id: int, industry_code: str) -> _Index | None:
    rows = (await db.execute(
        select(Chunk.id, Chunk.text).where(
            Chunk.tenant_id == tenant_id,
            Chunk.industry_code == industry_code,
            Chunk.is_active == True,
        )
    )).all()
    if not rows:
        return None
    corpus = [_tokenize(r[1]) for r in rows]
    if not any(corpus):
        return None
    bm25 = BM25Okapi(corpus)
    return _Index(bm25=bm25, chunk_ids=[r[0] for r in rows])


async def search(
    db: AsyncSession,
    tenant_id: int,
    industry_codes: list[str],
    query: str,
    top_k: int = 20,
    include_platform: bool = True,
) -> list[dict]:
    """Returns [{chunk_id, score}], merged across (tenant, industry) and PLATFORM."""
    tenant_ids = [tenant_id]
    if include_platform and tenant_id != 0:
        tenant_ids.append(0)

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    out: list[dict] = []
    for tid in tenant_ids:
        for ic in industry_codes:
            key = _key(tid, ic)
            with _lock:
                idx = _cache.get(key)
            if idx is None:
                idx = await _build(db, tid, ic)
                if idx is None:
                    continue
                with _lock:
                    _cache[key] = idx
            scores = idx.bm25.get_scores(q_tokens)
            for cid, sc in zip(idx.chunk_ids, scores):
                if sc > 0:
                    out.append({"chunk_id": int(cid), "score": float(sc)})
    out.sort(key=lambda x: -x["score"])
    return out[:top_k]
