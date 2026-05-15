"""Chunk-level operations: edit / toggle / split / merge.
All ops keep Qdrant in sync: re-embed on text change, delete/upsert as needed.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document
from app.services import bm25, embeddings, vector_store


def _payload(c: Chunk) -> dict:
    return {
        "kind": "chunk",
        "tenant_id": int(c.tenant_id),
        "industry_code": c.industry_code,
        "scope": c.scope,
        "document_id": int(c.document_id),
        "knowledge_set_id": int(c.knowledge_set_id) if c.knowledge_set_id else 0,
        "chunk_id": int(c.id),
        "is_active": bool(c.is_active),
        "text": c.text[:1000],
    }


async def _reindex_one(db: AsyncSession, c: Chunk) -> None:
    if c.qdrant_point_id:
        vector_store.delete_by_ids([c.qdrant_point_id])
        c.qdrant_point_id = ""
    if c.is_active and c.text.strip():
        vec = embeddings.embed_one(c.text)
        ids = vector_store.upsert_chunks([{"vector": vec, "payload": _payload(c)}])
        c.qdrant_point_id = ids[0]
    await db.flush()


async def edit(db: AsyncSession, c: Chunk, new_text: str) -> Chunk:
    c.text = new_text
    c.edited = True
    await _reindex_one(db, c)
    await db.commit()
    await db.refresh(c)
    bm25.invalidate(c.tenant_id, c.industry_code)
    return c


async def toggle(db: AsyncSession, c: Chunk, is_active: bool) -> Chunk:
    c.is_active = is_active
    await _reindex_one(db, c)
    await db.commit()
    await db.refresh(c)
    bm25.invalidate(c.tenant_id, c.industry_code)
    return c


async def split(db: AsyncSession, c: Chunk, position: int) -> list[Chunk]:
    """Split text at character position. Returns [first, second]."""
    if position <= 0 or position >= len(c.text):
        raise ValueError("position must be inside the chunk text")
    left, right = c.text[:position], c.text[position:]

    c.text = left
    c.edited = True
    await _reindex_one(db, c)

    # shift later chunks' index by +1 in same document
    later = (await db.execute(
        select(Chunk).where(Chunk.document_id == c.document_id, Chunk.chunk_index > c.chunk_index)
        .order_by(Chunk.chunk_index)
    )).scalars().all()
    for x in later:
        x.chunk_index += 1
    await db.flush()

    new = Chunk(
        tenant_id=c.tenant_id, industry_code=c.industry_code, scope=c.scope,
        document_id=c.document_id, knowledge_set_id=c.knowledge_set_id,
        chunk_index=c.chunk_index + 1, text=right, is_active=c.is_active, edited=True,
    )
    db.add(new); await db.flush()
    await _reindex_one(db, new)

    # update parent doc count
    doc = await db.get(Document, c.document_id)
    if doc:
        doc.chunk_count = (doc.chunk_count or 0) + 1
    await db.commit()
    await db.refresh(c); await db.refresh(new)
    bm25.invalidate(c.tenant_id, c.industry_code)
    return [c, new]


async def merge(db: AsyncSession, ids: list[int]) -> Chunk:
    """Merge N chunks (must belong to same document, contiguous order)."""
    if len(ids) < 2:
        raise ValueError("need at least 2 chunks to merge")
    rows = (await db.execute(select(Chunk).where(Chunk.id.in_(ids)))).scalars().all()
    if len(rows) != len(ids):
        raise ValueError("some chunks not found")
    doc_ids = {r.document_id for r in rows}
    if len(doc_ids) != 1:
        raise ValueError("chunks must belong to the same document")
    rows.sort(key=lambda r: r.chunk_index)
    keeper = rows[0]
    keeper.text = "\n".join(r.text for r in rows)
    keeper.edited = True

    # delete others (Qdrant + DB)
    drop_pids = [r.qdrant_point_id for r in rows[1:] if r.qdrant_point_id]
    if drop_pids:
        vector_store.delete_by_ids(drop_pids)
    for r in rows[1:]:
        await db.delete(r)
    await db.flush()

    await _reindex_one(db, keeper)

    # rebase later chunk indices (keep contiguous)
    n_removed = len(rows) - 1
    later = (await db.execute(
        select(Chunk).where(Chunk.document_id == keeper.document_id,
                            Chunk.chunk_index > rows[-1].chunk_index)
        .order_by(Chunk.chunk_index)
    )).scalars().all()
    for x in later:
        x.chunk_index -= n_removed

    doc = await db.get(Document, keeper.document_id)
    if doc:
        doc.chunk_count = max(0, (doc.chunk_count or 0) - n_removed)
    await db.commit()
    await db.refresh(keeper)
    bm25.invalidate(keeper.tenant_id, keeper.industry_code)
    return keeper
