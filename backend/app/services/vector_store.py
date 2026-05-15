"""Qdrant client wrapper with tenant + industry filtering."""
import uuid
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import settings


@lru_cache
def get_client() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL, prefer_grpc=False)


def ensure_collection() -> None:
    client = get_client()
    if not client.collection_exists(settings.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=qm.VectorParams(size=settings.EMBEDDING_DIM, distance=qm.Distance.COSINE),
        )
    # payload indexes for fast filter (idempotent)
    int_fields = ["tenant_id", "document_id", "knowledge_set_id", "chunk_id", "faq_id"]
    kw_fields = ["industry_code", "scope", "kind"]
    for f in int_fields:
        try:
            client.create_payload_index(settings.QDRANT_COLLECTION, f, qm.PayloadSchemaType.INTEGER)
        except Exception:
            pass
    for f in kw_fields:
        try:
            client.create_payload_index(settings.QDRANT_COLLECTION, f, qm.PayloadSchemaType.KEYWORD)
        except Exception:
            pass
    try:
        client.create_payload_index(settings.QDRANT_COLLECTION, "is_active", qm.PayloadSchemaType.BOOL)
    except Exception:
        pass


def upsert_chunks(points: list[dict]) -> list[str]:
    """points: [{vector, payload}], returns list of qdrant point ids."""
    client = get_client()
    ensure_collection()
    qpoints = []
    ids = []
    for p in points:
        pid = str(uuid.uuid4())
        ids.append(pid)
        qpoints.append(qm.PointStruct(id=pid, vector=p["vector"], payload=p["payload"]))
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=qpoints)
    return ids


def delete_by_document(document_id: int) -> None:
    client = get_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))])
        ),
    )


def delete_by_faq(faq_id: int) -> None:
    client = get_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(must=[qm.FieldCondition(key="faq_id", match=qm.MatchValue(value=faq_id))])
        ),
    )


def delete_by_ids(point_ids: list[str]) -> None:
    if not point_ids:
        return
    client = get_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=qm.PointIdsList(points=point_ids),
    )


def search(
    vector: list[float],
    tenant_id: int,
    industry_codes: list[str],
    top_k: int = 20,
    knowledge_set_ids: list[int] | None = None,
    include_platform: bool = True,
    kind: str | None = None,
) -> list[dict]:
    """Hybrid scope: tenant's PRIVATE + PLATFORM PUBLIC, both filtered to industry."""
    client = get_client()
    ensure_collection()

    industry_cond = qm.FieldCondition(key="industry_code", match=qm.MatchAny(any=industry_codes))
    active_cond = qm.FieldCondition(key="is_active", match=qm.MatchValue(value=True))

    tenant_ids = [tenant_id]
    if include_platform and tenant_id != 0:
        tenant_ids.append(0)
    tenant_cond = qm.FieldCondition(key="tenant_id", match=qm.MatchAny(any=tenant_ids))

    must = [industry_cond, active_cond, tenant_cond]
    if knowledge_set_ids:
        must.append(qm.FieldCondition(key="knowledge_set_id", match=qm.MatchAny(any=knowledge_set_ids)))
    if kind:
        must.append(qm.FieldCondition(key="kind", match=qm.MatchValue(value=kind)))

    flt = qm.Filter(must=must)

    res = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=vector,
        query_filter=flt,
        limit=top_k,
        with_payload=True,
    )
    return [
        {"id": str(p.id), "score": float(p.score), "payload": dict(p.payload or {})}
        for p in res.points
    ]
