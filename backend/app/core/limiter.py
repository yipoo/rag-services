"""Rate limiter. Keyed by (tenant_id, user_id) when authenticated, otherwise client IP."""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key(request: Request) -> str:
    # Prefer tenant+user when known (set by auth dependency); fallback to IP.
    auth = request.headers.get("authorization", "")
    tenant = request.headers.get("x-tenant-id", "")
    if auth:
        # use last 16 chars of token as cheap proxy for user
        return f"u:{tenant}:{auth[-16:]}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_key, default_limits=["120/minute"])
