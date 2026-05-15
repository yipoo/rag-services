"""Local embedding via fastembed (CPU, ONNX). bge-small-zh-v1.5 by default."""
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.core.config import settings


def model_cache_dir() -> Path:
    """Stable cache root for all local models. Default ~/.cache/rag-services/models.
    Override with MODEL_CACHE_DIR env or by passing a path."""
    base = settings.MODEL_CACHE_DIR.strip()
    if base:
        p = Path(base).expanduser()
    else:
        p = Path.home() / ".cache" / "rag-services" / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


# Point huggingface_hub & sentence-transformers to the same root so the rerank model
# also lands in our stable cache. Setting at import-time is important — these libs
# read env vars on first use.
_HF_HOME = model_cache_dir() / "huggingface"
_HF_HOME.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_HF_HOME))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(_HF_HOME / "sentence_transformers"))


@lru_cache
def _model():
    from fastembed import TextEmbedding
    fe_cache = model_cache_dir() / "fastembed"
    fe_cache.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=settings.EMBEDDING_MODEL, cache_dir=str(fe_cache))


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    texts = list(texts)
    if not texts:
        return []
    # convert numpy float32 -> plain Python float (JSON-serializable, smaller payload)
    return [[float(x) for x in v] for v in _model().embed(texts)]


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]
