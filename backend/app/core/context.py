from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequestContext:
    """Per-request tenant + industry context. Constructed once at the entry layer
    and passed (read-only) through the pipeline."""

    user_id: int
    tenant_id: int
    industry_code: str
    industry_codes: list[str] = field(default_factory=list)  # retrieval scope
    is_platform_admin: bool = False
    role: str = "viewer"
