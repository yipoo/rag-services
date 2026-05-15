from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # education / catering / drycleaning
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    default_prompt: Mapped[str] = mapped_column(Text, default="")
    # When confidence < handoff_threshold, mark suggest_handoff=True (UI hint, not enforced).
    # In soft_mode the bot still tries to answer; only at extremely low scores do we hand off.
    handoff_threshold: Mapped[float] = mapped_column(default=0.3)
    # Anything below record_threshold gets logged for ops to review.
    record_threshold: Mapped[float] = mapped_column(default=0.7)
    # Soft mode: keep replying gently even at low confidence, append a hedge line.
    # Strict mode (later, when KB is mature): explicit refusal at low confidence.
    soft_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
