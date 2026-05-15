"""Optional cross-encoder rerank. Lazy-loaded; falls back to identity if model unavailable.

Default model: BAAI/bge-reranker-v2-m3 via sentence-transformers (~600MB, downloaded on first use).
Set RERANK_ENABLED=false in .env to skip entirely.
"""
import threading

import structlog

from app.core.config import settings

log = structlog.get_logger()

_model = None
_model_lock = threading.Lock()
_load_failed = False


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _model_lock:
        if _model is not None or _load_failed:
            return _model
        try:
            # Import embeddings first so the HF_HOME env is set before
            # sentence_transformers reads it.
            from app.services import embeddings  # noqa: F401
            from sentence_transformers import CrossEncoder
            _model = CrossEncoder(
                settings.RERANK_MODEL,
                max_length=512,
                cache_folder=str(embeddings.model_cache_dir() / "huggingface" / "sentence_transformers"),
            )
            log.info("reranker.loaded", model=settings.RERANK_MODEL)
        except Exception as e:
            log.warning("reranker.load_failed", error=str(e))
            _load_failed = True
            _model = None
    return _model


def rerank(query: str, candidates: list[dict], text_key: str = "text",
           top_k: int | None = None) -> list[dict]:
    """Rerank candidates by (query, candidate.text) cross-encoder score.
    Adds 'rerank_score' to each candidate. If model unavailable, returns input unchanged."""
    if not settings.RERANK_ENABLED or not candidates:
        return candidates[:top_k] if top_k else candidates
    model = _get_model()
    if model is None:
        return candidates[:top_k] if top_k else candidates

    pairs = [(query, c.get(text_key, "")) for c in candidates]
    scores = model.predict(pairs)
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    candidates.sort(key=lambda x: -x.get("rerank_score", 0))
    return candidates[:top_k] if top_k else candidates
