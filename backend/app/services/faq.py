"""FAQ indexing: each (question + each similar) is one Qdrant point pointing at the FAQ."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FAQ
from app.services import embeddings, vector_store


def _faq_payload(f: FAQ, text: str) -> dict:
    return {
        "kind": "faq",
        "tenant_id": int(f.tenant_id),
        "industry_code": f.industry_code,
        "scope": f.scope,
        "knowledge_set_id": int(f.knowledge_set_id) if f.knowledge_set_id else 0,
        "faq_id": int(f.id),
        "is_active": bool(f.is_active),
        "text": text[:500],
    }


async def reindex(db: AsyncSession, faq: FAQ) -> None:
    """Drop and rebuild Qdrant points for this FAQ."""
    if faq.qdrant_point_ids:
        vector_store.delete_by_faq(faq.id)

    if not faq.is_active:
        faq.qdrant_point_ids = []
        await db.commit()
        return

    questions = [faq.question] + [q for q in (faq.similar_questions or []) if q.strip()]
    vectors = embeddings.embed_texts(questions)
    points = [{"vector": v, "payload": _faq_payload(faq, q)} for q, v in zip(questions, vectors)]
    ids = vector_store.upsert_chunks(points)
    faq.qdrant_point_ids = ids
    await db.commit()


def remove(faq: FAQ) -> None:
    if faq.qdrant_point_ids:
        vector_store.delete_by_faq(faq.id)
