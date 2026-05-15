from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Integer, Text, JSON, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


# Sentinel tenant_id for platform-owned (PUBLIC) knowledge.
PLATFORM_TENANT_ID = 0


class KnowledgeSet(Base):
    """A folder grouping documents within a (tenant, industry)."""

    __tablename__ = "knowledge_sets"
    __table_args__ = (
        Index("ix_kset_tenant_industry", "tenant_id", "industry_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)  # 0 = PLATFORM
    industry_code: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="PRIVATE")  # PRIVATE | PUBLIC
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[float] = mapped_column(default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_doc_tenant_industry_status", "tenant_id", "industry_code", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    industry_code: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="PRIVATE")
    knowledge_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_sets.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(32))  # file/url/manual/faq
    source_url: Mapped[str] = mapped_column(Text, default="")
    file_key: Mapped[str] = mapped_column(String(512), default="")  # MinIO object key
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending / parsing / parsed / publishing / published / failed / archived
    error_message: Mapped[str] = mapped_column(Text, default="")

    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunk_doc", "document_id"),
        Index("ix_chunk_tenant_industry", "tenant_id", "industry_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    industry_code: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="PRIVATE")

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    knowledge_set_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    qdrant_point_id: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)  # manually edited
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FAQ(Base):
    __tablename__ = "faqs"
    __table_args__ = (
        Index("ix_faq_tenant_industry", "tenant_id", "industry_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    industry_code: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="PRIVATE")
    knowledge_set_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    similar_questions: Mapped[list] = mapped_column(JSON, default=list)
    qdrant_point_ids: Mapped[list] = mapped_column(JSON, default=list)  # one per (q + similars)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
