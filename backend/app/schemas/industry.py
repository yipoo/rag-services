from pydantic import BaseModel


class IndustryCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    icon: str = ""
    default_prompt: str = ""
    handoff_threshold: float = 0.3
    record_threshold: float = 0.7
    soft_mode: bool = True


class IndustryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    default_prompt: str | None = None
    handoff_threshold: float | None = None
    record_threshold: float | None = None
    soft_mode: bool | None = None
    is_active: bool | None = None


class IndustryOut(BaseModel):
    id: int
    code: str
    name: str
    description: str
    icon: str
    is_active: bool
    default_prompt: str
    handoff_threshold: float
    record_threshold: float
    soft_mode: bool

    class Config:
        from_attributes = True
