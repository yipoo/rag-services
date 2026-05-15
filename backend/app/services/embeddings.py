"""Local embedding via fastembed (CPU, ONNX). bge-small-zh-v1.5 by default."""
from functools import lru_cache
from typing import Iterable

from app.core.config import settings


@lru_cache
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=settings.EMBEDDING_MODEL)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    texts = list(texts)
    if not texts:
        return []
    # convert numpy float32 -> plain Python float (JSON-serializable, smaller payload)
    return [[float(x) for x in v] for v in _model().embed(texts)]


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]
