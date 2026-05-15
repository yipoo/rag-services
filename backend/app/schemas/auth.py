from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    name: str
    is_platform_admin: bool


class TenantBrief(BaseModel):
    id: int
    code: str
    name: str
    role: str
    default_industry_code: str | None
    industries: list[str]


class MeResponse(BaseModel):
    id: int
    email: str
    name: str
    is_platform_admin: bool
    tenants: list[TenantBrief]
