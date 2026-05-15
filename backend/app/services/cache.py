"""Semantic cache for chat answers.

Strategy: store (vector, answer) per (tenant_id, industry_code). On lookup, find the
most-similar prior question; if cosine >= threshold, return cached answer.

Backed by Redis sorted sets + hashes for simplicity. Evicts via TTL. For high-scale, switch
to a dedicated vector store namespace, but this works fine for MVP.
"""
import hashlib
import json
import time
from functools import lru_cache

import redis.asyncio as aioredis
import structlog

from app.core.config import settings
from app.services import embeddings

log = structlog.get_logger()


@lru_cache
def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=False)


def _key(tenant_id: int, industry_code: str) -> str:
    return f"semcache:{tenant_id}:{industry_code}"


def _cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1
    nb = sum(x * x for x in b) ** 0.5 or 1
    return s / (na * nb)


async def lookup(tenant_id: int, industry_code: str, question: str) -> dict | None:
    """Return cached {answer, question, score, age_s} if a similar question is cached."""
    if not settings.CACHE_ENABLED:
        return None
    r = _redis()
    qvec = embeddings.embed_one(question)
    # iterate cached entries (small N expected; for larger, switch to ANN)
    members = await r.smembers(_key(tenant_id, industry_code) + ":ids")
    best = None
    best_score = -1.0
    for m in members:
        raw = await r.get(_key(tenant_id, industry_code) + ":" + m.decode())
        if not raw:
            continue
        entry = json.loads(raw)
        sc = _cosine(qvec, entry["vec"])
        if sc > best_score:
            best_score = sc
            best = entry
    if best and best_score >= settings.CACHE_SIM_THRESHOLD:
        return {
            "answer": best["answer"],
            "question": best["question"],
            "score": best_score,
            "age_s": int(time.time() - best.get("ts", 0)),
        }
    return None


async def store(tenant_id: int, industry_code: str, question: str, answer: str) -> None:
    if not settings.CACHE_ENABLED or not answer.strip():
        return
    r = _redis()
    qvec = [float(x) for x in embeddings.embed_one(question)]
    h = hashlib.sha1(question.encode("utf-8")).hexdigest()[:16]
    entry = {"question": question, "answer": answer, "vec": qvec, "ts": int(time.time())}
    await r.set(_key(tenant_id, industry_code) + ":" + h, json.dumps(entry),
                ex=settings.CACHE_TTL_SECONDS)
    await r.sadd(_key(tenant_id, industry_code) + ":ids", h)
    await r.expire(_key(tenant_id, industry_code) + ":ids", settings.CACHE_TTL_SECONDS)


async def clear(tenant_id: int, industry_code: str) -> int:
    r = _redis()
    members = await r.smembers(_key(tenant_id, industry_code) + ":ids")
    n = 0
    for m in members:
        if await r.delete(_key(tenant_id, industry_code) + ":" + m.decode()):
            n += 1
    await r.delete(_key(tenant_id, industry_code) + ":ids")
    return n
