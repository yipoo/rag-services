"""Smoke test that the security hardening actually blocks unsafe inputs."""
import asyncio
import io
import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ["RERANK_ENABLED"] = "false"
os.environ["CACHE_ENABLED"] = "false"
os.environ["APP_ENV"] = "dev"  # so SECRET_KEY default only warns
os.environ["SECRET_KEY"] = "x" * 32  # pass startup checks anyway
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "strong-pass-987654"
os.environ["MAX_UPLOAD_BYTES"] = "1024"  # tiny for testing
os.environ["MAX_CSV_ROWS"] = "3"

# Stub fastembed
fe = types.ModuleType("fastembed")
class _TE:
    def __init__(self, **kw): pass
    def embed(self, texts): return [[0.1]*512 for _ in texts]
fe.TextEmbedding = _TE
sys.modules["fastembed"] = fe

# Stub MinIO, Qdrant, LLM, redis as before
import app.services.storage as st_mod
st_mod.ensure_bucket = lambda: None
st_mod.put_object = lambda *a, **k: None
st_mod.get_object = lambda k: b""

import app.services.vector_store as vs
vs.ensure_collection = lambda: None
vs.upsert_chunks = lambda points: ["id"] * len(points)
vs.search = lambda **k: []
vs.delete_by_document = lambda *a: None
vs.delete_by_ids = lambda *a: None
vs.delete_by_faq = lambda *a: None

import app.services.llm as llm_mod
async def _chat(messages, **kw): return "ok"
async def _stream(messages, **kw):
    if False: yield ""
llm_mod.chat = _chat
llm_mod.chat_stream = _stream

import app.services.cache as cache_mod
class _FR:
    async def set(self,*a,**k): pass
    async def get(self,*a): return None
    async def sadd(self,*a,**k): pass
    async def smembers(self,*a): return set()
    async def expire(self,*a,**k): pass
    async def delete(self,*a): return 0
cache_mod._redis = lambda: _FR()


from httpx import ASGITransport, AsyncClient
from app.main import app, _bootstrap


async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cli:
        await _bootstrap()
        r = await cli.post("/api/auth/login", json={"email": "admin@example.com", "password": "strong-pass-987654"})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        me = (await cli.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        tid = me["tenants"][0]["id"]
        TH = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(tid), "X-Industry": "education"}

        # --- SSRF: localhost ---
        r = await cli.post("/api/documents/url", headers=TH, json={"url": "http://localhost:8000/health"})
        assert r.status_code == 400 and "Unsafe URL" in r.json()["detail"], r.text
        print("✓ SSRF: blocked http://localhost")

        # SSRF: cloud metadata
        r = await cli.post("/api/documents/url", headers=TH, json={"url": "http://169.254.169.254/"})
        assert r.status_code == 400, r.text
        print("✓ SSRF: blocked metadata IP")

        # SSRF: file://
        r = await cli.post("/api/documents/url", headers=TH, json={"url": "file:///etc/passwd"})
        # could be 422 (pydantic url validator) or 400; either is acceptable
        assert r.status_code in (400, 422), r.text
        print("✓ SSRF: blocked file:// scheme")

        # --- file upload limits ---
        # too big
        big = b"x" * 2000
        files = {"file": ("big.txt", io.BytesIO(big), "text/plain")}
        r = await cli.post("/api/documents/upload", headers=TH, files=files)
        assert r.status_code == 400 and "too large" in r.json()["detail"], r.text
        print("✓ Upload size: rejected >1024 bytes")

        # bad extension
        files = {"file": ("evil.exe", io.BytesIO(b"x"), "application/octet-stream")}
        r = await cli.post("/api/documents/upload", headers=TH, files=files)
        assert r.status_code == 400 and "Unsupported" in r.json()["detail"], r.text
        print("✓ Upload ext: rejected .exe")

        # filename with path traversal — should be sanitized, not rejected
        files = {"file": ("../../etc/passwd.txt", io.BytesIO(b"hello"), "text/plain")}
        r = await cli.post("/api/documents/upload", headers=TH, files=files)
        # 200 or 400 depending on whether the basename has an allowed ext - .txt is allowed
        assert r.status_code == 200, r.text
        # title should not contain path separators
        assert ".." not in r.json()["title"] and "/" not in r.json()["title"]
        print(f"✓ Upload filename: sanitized -> {r.json()['title']!r}")

        # --- CSV limits ---
        big_csv = "question,answer\n" + "\n".join(f"q{i},a{i}" for i in range(10))
        files = {"file": ("f.csv", io.BytesIO(big_csv.encode()), "text/csv")}
        r = await cli.post("/api/faqs/import", headers=TH, files=files)
        assert r.status_code == 400 and "max rows" in r.json()["detail"], r.text
        print(f"✓ CSV rows: rejected (cap=3)")

        print("\n🎉 ALL SECURITY ASSERTIONS PASSED")


asyncio.run(main())
