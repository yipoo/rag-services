from datetime import datetime
from pydantic import BaseModel


class KnowledgeSetCreate(BaseModel):
    name: str
    description: str = ""
    weight: float = 1.0


class KnowledgeSetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    weight: float | None = None


class KnowledgeSetOut(BaseModel):
    id: int
    tenant_id: int
    industry_code: str
    scope: str
    name: str
    description: str
    is_active: bool
    weight: float
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id: int
    tenant_id: int
    industry_code: str
    scope: str
    knowledge_set_id: int | None
    title: str
    source_type: str
    mime_type: str
    size_bytes: int
    status: str
    error_message: str
    chunk_count: int
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentManualCreate(BaseModel):
    title: str
    content: str
    knowledge_set_id: int | None = None


class DocumentURLCreate(BaseModel):
    url: str
    title: str | None = None
    knowledge_set_id: int | None = None


class ChunkOut(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    text: str
    is_active: bool

    class Config:
        from_attributes = True


class FAQCreate(BaseModel):
    question: str
    answer: str
    similar_questions: list[str] = []
    knowledge_set_id: int | None = None


class FAQOut(BaseModel):
    id: int
    question: str
    answer: str
    similar_questions: list[str]
    is_active: bool
    hit_count: int
    knowledge_set_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True
