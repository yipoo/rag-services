import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.deps import Ctx, DBSession
from app.models import Chunk, Document
from app.schemas.knowledge import ChunkOut, DocumentManualCreate, DocumentOut, DocumentURLCreate
from app.services import document_pipeline, storage

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _new_doc(ctx, *, title: str, source_type: str, **kwargs) -> Document:
    return Document(
        tenant_id=ctx.tenant_id,
        industry_code=ctx.industry_code,
        scope="PUBLIC" if ctx.tenant_id == 0 else "PRIVATE",
        title=title,
        source_type=source_type,
        status="pending",
        **kwargs,
    )


async def _kick_processing(db_session_factory, document_id: int):
    """Background task: open a NEW DB session, since the request session is closed."""
    from app.core.db import SessionLocal
    async with SessionLocal() as session:
        await document_pipeline.process_document(session, document_id)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    db: DBSession,
    ctx: Ctx,
    knowledge_set_id: int | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    q = select(Document).where(
        Document.tenant_id == ctx.tenant_id,
        Document.industry_code == ctx.industry_code,
    )
    if knowledge_set_id is not None:
        q = q.where(Document.knowledge_set_id == knowledge_set_id)
    if status_filter:
        q = q.where(Document.status == status_filter)
    q = q.order_by(Document.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/upload", response_model=DocumentOut)
async def upload_file(
    db: DBSession,
    ctx: Ctx,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_set_id: Annotated[int | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
):
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    key = f"t{ctx.tenant_id}/{ctx.industry_code}/{uuid.uuid4()}-{file.filename}"
    storage.put_object(key, data, file.content_type or "application/octet-stream")

    doc = _new_doc(
        ctx,
        title=title or file.filename or "untitled",
        source_type="file",
        file_key=key,
        mime_type=file.content_type or "",
        size_bytes=len(data),
        knowledge_set_id=knowledge_set_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    background.add_task(_kick_processing, None, doc.id)
    return doc


@router.post("/manual", response_model=DocumentOut)
async def create_manual(req: DocumentManualCreate, db: DBSession, ctx: Ctx, background: BackgroundTasks):
    doc = _new_doc(
        ctx,
        title=req.title,
        source_type="manual",
        knowledge_set_id=req.knowledge_set_id,
        extra={"content": req.content},
        size_bytes=len(req.content.encode("utf-8")),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    background.add_task(_kick_processing, None, doc.id)
    return doc


@router.post("/url", response_model=DocumentOut)
async def create_url(req: DocumentURLCreate, db: DBSession, ctx: Ctx, background: BackgroundTasks):
    doc = _new_doc(
        ctx,
        title=req.title or req.url,
        source_type="url",
        source_url=req.url,
        knowledge_set_id=req.knowledge_set_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    background.add_task(_kick_processing, None, doc.id)
    return doc


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
async def reprocess(doc_id: int, db: DBSession, ctx: Ctx, background: BackgroundTasks):
    doc = await db.get(Document, doc_id)
    if not doc or doc.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    background.add_task(_kick_processing, None, doc.id)
    return doc


@router.delete("/{doc_id}")
async def delete_doc(doc_id: int, db: DBSession, ctx: Ctx):
    doc = await db.get(Document, doc_id)
    if not doc or doc.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    from app.services import vector_store
    vector_store.delete_by_document(doc.id)
    await db.delete(doc)
    await db.commit()
    return {"ok": True}


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(doc_id: int, db: DBSession, ctx: Ctx):
    doc = await db.get(Document, doc_id)
    if not doc or doc.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    rows = (await db.execute(
        select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index)
    )).scalars().all()
    return rows
