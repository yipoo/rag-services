"""Startup safety checks. Refuses to boot with insecure defaults in non-dev environments."""
import re

import structlog

from app.core.config import settings

log = structlog.get_logger()

_INSECURE_SECRET_KEYS = {
    "change-me",
    "change-me-please-use-a-long-random-string",
    "",
}
_INSECURE_ADMIN_PASSWORDS = {"admin", "admin123", "admin123456", "password", "123456"}


class InsecureConfigError(RuntimeError):
    pass


def run_startup_checks() -> list[str]:
    """Returns a list of warnings. Raises InsecureConfigError on hard fails in non-dev envs."""
    warnings: list[str] = []
    errors: list[str] = []
    is_dev = settings.APP_ENV.lower() in ("dev", "development", "local")

    # SECRET_KEY
    sk = (settings.SECRET_KEY or "").strip()
    if sk.lower() in _INSECURE_SECRET_KEYS or len(sk) < 24:
        msg = f"SECRET_KEY is insecure (length={len(sk)}). Set a long random value in .env."
        (warnings if is_dev else errors).append(msg)

    # Bootstrap admin password
    pw = settings.BOOTSTRAP_ADMIN_PASSWORD or ""
    if pw.lower() in _INSECURE_ADMIN_PASSWORDS or len(pw) < 8:
        msg = f"BOOTSTRAP_ADMIN_PASSWORD is weak (length={len(pw)}). Use at least 12 strong chars."
        (warnings if is_dev else errors).append(msg)

    # MinIO default creds (only check in prod)
    if not is_dev:
        if settings.S3_ACCESS_KEY == "minioadmin" or settings.S3_SECRET_KEY == "minioadmin":
            errors.append("S3_ACCESS_KEY/S3_SECRET_KEY use default MinIO credentials.")

    # CORS wildcard in prod
    if not is_dev and settings.CORS_ORIGINS.strip() == "*":
        errors.append("CORS_ORIGINS=* is not allowed in non-dev environments.")

    # SSRF
    if not is_dev and settings.URL_CRAWL_ALLOW_PRIVATE:
        errors.append("URL_CRAWL_ALLOW_PRIVATE=true is not allowed in non-dev environments.")

    for w in warnings:
        log.warning("safety.warning", message=w)

    if errors and not settings.DISABLE_SAFETY_CHECKS:
        for e in errors:
            log.error("safety.error", message=e)
        raise InsecureConfigError(
            "Refusing to start with insecure configuration:\n  - "
            + "\n  - ".join(errors)
            + "\n\nFix .env or set DISABLE_SAFETY_CHECKS=true (NOT recommended)."
        )

    return warnings + errors
