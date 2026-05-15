"""Validate uploaded files: size, extension, filename safety."""
import pathlib
import re

from app.core.config import settings


class UnsafeFileError(ValueError):
    pass


_FILENAME_SANITIZE_RE = re.compile(r"[^\w\.\-]+", re.UNICODE)


def sanitize_filename(name: str | None) -> str:
    name = (name or "").strip().replace("\x00", "")
    if not name:
        return "untitled"
    # strip any path components — only the basename
    name = pathlib.PurePosixPath(name).name
    name = pathlib.PureWindowsPath(name).name
    name = _FILENAME_SANITIZE_RE.sub("_", name)
    return name[:200] or "untitled"


def allowed_exts() -> set[str]:
    return {e.strip().lower() for e in settings.ALLOWED_UPLOAD_EXTS.split(",") if e.strip()}


def check_filename(name: str) -> str:
    ext = pathlib.Path(name).suffix.lower()
    if ext not in allowed_exts():
        raise UnsafeFileError(f"Unsupported file type: {ext or '(none)'}. Allowed: {sorted(allowed_exts())}")
    return ext


def check_size(size: int | None, *, label: str = "file") -> None:
    if size is not None and size > settings.MAX_UPLOAD_BYTES:
        raise UnsafeFileError(
            f"{label} too large: {size} bytes (max {settings.MAX_UPLOAD_BYTES})"
        )


def check_bytes(data: bytes, *, label: str = "file") -> None:
    if not data:
        raise UnsafeFileError(f"{label} is empty")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise UnsafeFileError(
            f"{label} too large: {len(data)} bytes (max {settings.MAX_UPLOAD_BYTES})"
        )
