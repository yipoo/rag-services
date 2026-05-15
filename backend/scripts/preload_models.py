"""Pre-download all local models into the stable cache.

Run once after install — subsequent backend startups won't redownload anything.

    PYTHONPATH=. .venv/bin/python scripts/preload_models.py

What it downloads:
- fastembed embedding model (~100MB)
- sentence-transformers cross-encoder rerank model (~600MB, optional)
- jieba dictionary (built into the package, no download)

Cache location: ~/.cache/rag-services/models/ (or $MODEL_CACHE_DIR)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _humansize(p: Path) -> str:
    if not p.exists():
        return "(missing)"
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    if total < 1024:
        return f"{total} B"
    if total < 1024 ** 2:
        return f"{total / 1024:.1f} KB"
    if total < 1024 ** 3:
        return f"{total / 1024 ** 2:.1f} MB"
    return f"{total / 1024 ** 3:.2f} GB"


def preload_embedding() -> None:
    from app.core.config import settings
    from app.services import embeddings

    cache = embeddings.model_cache_dir() / "fastembed"
    print(f"\n[1/2] Embedding model: {settings.EMBEDDING_MODEL}")
    print(f"      Cache:           {cache}")
    t0 = time.time()
    vec = embeddings.embed_one("preload warmup 你好")
    print(f"      ✓ ready (dim={len(vec)}, took {time.time()-t0:.1f}s, size={_humansize(cache)})")


def preload_reranker() -> None:
    from app.core.config import settings

    if not settings.RERANK_ENABLED:
        print("\n[2/2] Reranker: SKIPPED (RERANK_ENABLED=false)")
        return

    from app.services import embeddings, reranker
    cache = embeddings.model_cache_dir() / "huggingface"
    print(f"\n[2/2] Rerank model:  {settings.RERANK_MODEL}")
    print(f"      Cache:         {cache}")
    print(f"      (first run downloads ~600MB, please wait...)")
    t0 = time.time()
    out = reranker.rerank("test query", [{"text": "test passage"}])
    if not out:
        print("      ⚠️  reranker returned empty — likely sentence-transformers not installed.")
        print("          Install with: pip install sentence-transformers")
        return
    print(f"      ✓ ready (took {time.time()-t0:.1f}s, size={_humansize(cache)})")


def main():
    # ensure repo root is importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from app.services import embeddings
    root = embeddings.model_cache_dir()
    print("=" * 60)
    print(" Model preloader")
    print(f" Cache root: {root}")
    print(f" Current size: {_humansize(root)}")
    print("=" * 60)

    preload_embedding()
    preload_reranker()

    print("\n" + "=" * 60)
    print(f" Done. Total cache size: {_humansize(root)}")
    print(" Future starts will reuse this cache — no more downloads.")
    print("=" * 60)


if __name__ == "__main__":
    main()
