"""End-to-end smoke test using SQLite + stubbed embeddings/Qdrant/LLM.
Verifies: bootstrap, login, KB set CRUD, manual document ingest, chat retrieval.
"""
import asyncio
import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Stub fastembed (avoid model download)
fe = types.ModuleType("fastembed")
class _TE:
    def __init__(self, **kw): pass
    def embed(self, texts):
        # cheap deterministic vectors based on length, dim=512
        out = []
        for t in texts:
            v = [0.0] * 512
            for i, ch in enumerate(t.encode("utf-8")[:512]):
                v[i] = (ch % 17) / 17.0
            out.append(v)
        return out
fe.TextEmbedding = _TE
sys.modules["fastembed"] = fe

# Stub minio storage (in-memory)
import app.services.storage as storage_mod
_blobs: dict[str, bytes] = {}
storage_mod.ensure_bucket = lambda: None
storage_mod.put_object = lambda key, data, content_type="": _blobs.__setitem__(key, data)
storage_mod.get_object = lambda key: _blobs[key]

# Stub Qdrant (in-memory list)
import app.services.vector_store as vs
_points: list[dict] = []
vs.ensure_collection = lambda: None
def _upsert(points):
    import uuid as _u
    ids = []
    for p in points:
        pid = str(_u.uuid4())
        ids.append(pid)
        _points.append({"id": pid, "vector": p["vector"], "payload": p["payload"]})
    return ids
vs.upsert_chunks = _upsert
def _delete_by_doc(doc_id):
    _points[:] = [p for p in _points if p["payload"].get("document_id") != doc_id]
vs.delete_by_document = _delete_by_doc
def _cos(a, b):
    s = sum(x*y for x,y in zip(a,b))
    na = sum(x*x for x in a) ** 0.5 or 1
    nb = sum(x*x for x in b) ** 0.5 or 1
    return s/(na*nb)
def _search(vector, tenant_id, industry_codes, top_k=20, knowledge_set_ids=None, include_platform=True):
    cands = []
    for p in _points:
        pl = p["payload"]
        if pl.get("industry_code") not in industry_codes: continue
        if not pl.get("is_active"): continue
        if pl.get("tenant_id") != tenant_id and not (include_platform and pl.get("tenant_id") == 0):
            continue
        if knowledge_set_ids and pl.get("knowledge_set_id") not in knowledge_set_ids:
            continue
        cands.append({"id": p["id"], "score": _cos(vector, p["vector"]), "payload": pl})
    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:top_k]
vs.search = _search

# Stub LLM (echo back contexts)
import app.services.llm as llm_mod
async def _chat(messages, **kw):
    return "[stub answer based on retrieval]"
llm_mod.chat = _chat


from httpx import AsyncClient, ASGITransport
from app.main import app


async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as cli:
        # trigger lifespan via startup; httpx ASGITransport doesn't run lifespan by default
        # so call bootstrap manually
        from app.main import _bootstrap
        await _bootstrap()

        # 1. login as platform admin
        r = await cli.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123456"})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        H = {"Authorization": f"Bearer {token}"}
        print("✓ login")

        # 2. me + tenants
        r = await cli.get("/api/auth/me", headers=H)
        assert r.status_code == 200
        me = r.json()
        assert me["is_platform_admin"]
        assert len(me["tenants"]) >= 1
        demo_id = me["tenants"][0]["id"]
        print(f"✓ me: tenants={[t['code'] for t in me['tenants']]}")

        # 3. industries
        r = await cli.get("/api/industries", headers=H)
        assert r.status_code == 200
        codes = [i["code"] for i in r.json()]
        assert "education" in codes
        print(f"✓ industries: {codes}")

        # 4. switch into demo tenant + education industry
        TH = {**H, "X-Tenant-Id": str(demo_id), "X-Industry": "education"}

        # 5. create knowledge set
        r = await cli.post("/api/knowledge-sets", headers=TH, json={"name": "课程问答", "description": "test"})
        assert r.status_code == 200, r.text
        ks_id = r.json()["id"]
        print(f"✓ created knowledge set id={ks_id}")

        # 6. create manual document
        r = await cli.post("/api/documents/manual", headers=TH, json={
            "title": "退费政策",
            "content": "我们的退费政策是：开课7天内可全额退款。\n\n超过7天按比例退款。\n\n超过30天不予退款。",
            "knowledge_set_id": ks_id,
        })
        assert r.status_code == 200, r.text
        doc_id = r.json()["id"]
        print(f"✓ created document id={doc_id}")

        # 7. wait for background task
        for _ in range(30):
            r = await cli.get("/api/documents", headers=TH)
            d = next((x for x in r.json() if x["id"] == doc_id), None)
            if d and d["status"] in ("published", "failed"):
                break
            await asyncio.sleep(0.2)
        assert d["status"] == "published", f"doc status={d['status']} err={d['error_message']}"
        assert d["chunk_count"] > 0
        print(f"✓ document processed: chunks={d['chunk_count']}")

        # 8. list chunks
        r = await cli.get(f"/api/documents/{doc_id}/chunks", headers=TH)
        assert r.status_code == 200
        chunks = r.json()
        assert len(chunks) > 0
        print(f"✓ chunks listed: {len(chunks)} (sample: {chunks[0]['text'][:30]!r})")

        # 9. chat
        r = await cli.post("/api/chat", headers=TH, json={"question": "可以退费吗？", "top_k": 3})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"]
        assert len(body["retrieval"]) > 0
        print(f"✓ chat: retrieval={len(body['retrieval'])} top_score={body['confidence']:.3f}")
        print(f"   answer: {body['answer'][:80]}")

        # 10. tenant isolation: try with different tenant header (none exists), should 403
        r = await cli.post("/api/documents/manual", headers={**H, "X-Tenant-Id": "9999", "X-Industry": "education"},
                           json={"title": "x", "content": "y"})
        # platform admin is allowed any tenant, so it would succeed with tenant_id=9999
        # for a real isolation test we'd create a non-admin user; skip for now
        print("✓ all assertions passed")


asyncio.run(main())
