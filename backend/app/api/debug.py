"""Retrieval-only debug endpoint: returns all stages without calling the LLM."""
from pydantic import BaseModel
from fastapi import APIRouter

from app.core.deps import Ctx, DBSession
from app.services import rag

router = APIRouter(prefix="/api/debug", tags=["debug"])


class RetrieveReq(BaseModel):
    question: str
    top_k: int = 5
    knowledge_set_ids: list[int] | None = None
    enable_faq_short_circuit: bool = True
    enable_rerank: bool = True


@router.post("/retrieve")
async def retrieve(req: RetrieveReq, db: DBSession, ctx: Ctx):
    return await rag.retrieve(
        db=db, ctx=ctx, question=req.question, top_k=req.top_k,
        knowledge_set_ids=req.knowledge_set_ids,
        enable_faq_short_circuit=req.enable_faq_short_circuit,
        enable_rerank=req.enable_rerank,
    )
