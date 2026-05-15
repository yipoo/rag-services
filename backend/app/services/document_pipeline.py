"""End-to-end document processing: parse -> chunk -> embed -> upsert."""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document
from app.services import bm25, chunker, embeddings, parser, storage, url_guard, vector_store

log = structlog.get_logger()


async def process_document(db: AsyncSession, document_id: int) -> None:
    doc = await db.get(Document, document_id)
    if not doc:
        return
    try:
        doc.status = "parsing"
        doc.error_message = ""
        await db.commit()

        # 1. fetch raw bytes
        if doc.source_type == "manual":
            text = doc.extra.get("content", "") if doc.extra else ""
        elif doc.source_type == "file":
            data = storage.get_object(doc.file_key)
            text = parser.parse_bytes(data, doc.mime_type, doc.title)
        elif doc.source_type == "url":
            import httpx
            url_guard.assert_safe_url(doc.source_url)
            # Disable automatic redirects so we can re-check each hop
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                cur = doc.source_url
                for _ in range(5):  # max 5 hops
                    url_guard.assert_safe_url(cur)
                    r = client.get(cur)
                    if r.is_redirect:
                        cur = str(r.next_request.url) if r.next_request else r.headers.get("location", "")
                        continue
                    r.raise_for_status()
                    break
                else:
                    raise ValueError("Too many redirects")
            # cap body size at 50MB
            body = r.content[: 50 * 1024 * 1024]
            text = parser.parse_bytes(body, r.headers.get("content-type", ""), doc.source_url)
        else:
            raise ValueError(f"Unknown source_type: {doc.source_type}")

        if not text or not text.strip():
            raise ValueError("No text extracted")

        # 2. chunk
        pieces = chunker.chunk_text(text)
        if not pieces:
            raise ValueError("No chunks produced")

        # 3. delete previous chunks (re-process)
        old = (await db.execute(select(Chunk).where(Chunk.document_id == doc.id))).scalars().all()
        for c in old:
            await db.delete(c)
        vector_store.delete_by_document(doc.id)
        await db.flush()

        # 4. embed
        vectors = embeddings.embed_texts(pieces)

        # 5. insert chunks
        chunk_rows: list[Chunk] = []
        for i, (txt, vec) in enumerate(zip(pieces, vectors)):
            chunk_rows.append(Chunk(
                tenant_id=doc.tenant_id,
                industry_code=doc.industry_code,
                scope=doc.scope,
                document_id=doc.id,
                knowledge_set_id=doc.knowledge_set_id,
                chunk_index=i,
                text=txt,
                is_active=True,
            ))
        db.add_all(chunk_rows)
        await db.flush()

        # 6. upsert to qdrant with payload
        points = []
        for c, vec in zip(chunk_rows, vectors):
            points.append({
                "vector": vec,
                "payload": {
                    "kind": "chunk",
                    "tenant_id": int(c.tenant_id),
                    "industry_code": c.industry_code,
                    "scope": c.scope,
                    "document_id": int(c.document_id),
                    "knowledge_set_id": int(c.knowledge_set_id) if c.knowledge_set_id else 0,
                    "chunk_id": int(c.id),
                    "is_active": True,
                    "text": c.text[:1000],
                },
            })
        ids = vector_store.upsert_chunks(points)
        for c, pid in zip(chunk_rows, ids):
            c.qdrant_point_id = pid

        doc.chunk_count = len(chunk_rows)
        doc.status = "published"
        doc.error_message = ""
        await db.commit()
        bm25.invalidate(doc.tenant_id, doc.industry_code)
        log.info("document.processed", doc_id=doc.id, chunks=len(chunk_rows))

    except Exception as e:
        await db.rollback()
        d2 = await db.get(Document, document_id)
        if d2:
            d2.status = "failed"
            d2.error_message = str(e)[:500]
            await db.commit()
        log.exception("document.process_failed", doc_id=document_id, error=str(e))
