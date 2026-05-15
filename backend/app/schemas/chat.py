from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    session_id: int | None = None
    top_k: int = 5
    knowledge_set_ids: list[int] | None = None
    debug: bool = False


class RetrievedChunk(BaseModel):
    chunk_id: int
    document_id: int
    score: float
    text: str
    document_title: str = ""


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    retrieval: list[RetrievedChunk]
    confidence: float
    suggest_handoff: bool
    debug: dict | None = None
