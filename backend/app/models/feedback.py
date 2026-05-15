from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, JSON, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UnansweredQuestion(Base):
    """Record any chat where confidence < record_threshold or 0 hits.

    Operations review these and either: convert to FAQ, dismiss, or supplement KB."""

    __tablename__ = "unanswered_questions"
    __table_args__ = (
        Index("ix_unans_tenant_industry", "tenant_id", "industry_code", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    industry_code: Mapped[str] = mapped_column(String(64), index=True)

    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    answer_given: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="llm")  # faq/llm/fallback/cache

    # category derived from confidence buckets:
    #   miss     - 0 retrieval results
    #   low      - score < record_threshold but > 0
    #   handoff  - explicit handoff suggested
    category: Mapped[str] = mapped_column(String(16), default="low", index=True)

    retrieval: Mapped[dict] = mapped_column(JSON, default=dict)  # {chunks: [...], scores: [...]}
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending / handled / dismissed
    handled_faq_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
