from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status

from app.core.deps import Ctx, DBSession
from app.models import Chunk
from app.schemas.knowledge import ChunkOut
from app.services import chunk_ops

router = APIRouter(prefix="/api/chunks", tags=["chunks"])


def _own(c: Chunk | None, ctx) -> Chunk:
    if not c or c.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chunk not found")
    return c


class ChunkEdit(BaseModel):
    text: str


@router.patch("/{chunk_id}", response_model=ChunkOut)
async def edit_chunk(chunk_id: int, req: ChunkEdit, db: DBSession, ctx: Ctx):
    c = _own(await db.get(Chunk, chunk_id), ctx)
    return await chunk_ops.edit(db, c, req.text)


class ToggleReq(BaseModel):
    is_active: bool


@router.post("/{chunk_id}/toggle", response_model=ChunkOut)
async def toggle_chunk(chunk_id: int, req: ToggleReq, db: DBSession, ctx: Ctx):
    c = _own(await db.get(Chunk, chunk_id), ctx)
    return await chunk_ops.toggle(db, c, req.is_active)


class SplitReq(BaseModel):
    position: int


@router.post("/{chunk_id}/split", response_model=list[ChunkOut])
async def split_chunk(chunk_id: int, req: SplitReq, db: DBSession, ctx: Ctx):
    c = _own(await db.get(Chunk, chunk_id), ctx)
    try:
        return await chunk_ops.split(db, c, req.position)
    except ValueError as e:
        raise HTTPException(400, str(e))


class MergeReq(BaseModel):
    chunk_ids: list[int]


@router.post("/merge", response_model=ChunkOut)
async def merge_chunks(req: MergeReq, db: DBSession, ctx: Ctx):
    # ownership check on the first one is sufficient since merge enforces same doc
    if not req.chunk_ids:
        raise HTTPException(400, "chunk_ids required")
    c = _own(await db.get(Chunk, req.chunk_ids[0]), ctx)
    try:
        return await chunk_ops.merge(db, req.chunk_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
