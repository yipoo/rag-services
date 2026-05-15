"""Smoke test for Phase 2/4 features:
hybrid retrieval, FAQ short-circuit, chunk edit/split/merge, semantic cache.

Stubs out fastembed, qdrant, MinIO, LLM, sentence-transformers, redis (in-memory).
"""
import asyncio
import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ["RERANK_ENABLED"] = "false"  # avoid sentence-transformers download
os.environ["CACHE_ENABLED"] = "true"

# --- stub fastembed ---
fe = types.ModuleType("fastembed")
class _TE:
    def __init__(self, **kw): pass
    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 512
            for i, ch in enumerate((t or "").encode("utf-8")[:512]):
                v[i] = (ch % 17) / 17.0
            out.append(v)
        return out
fe.TextEmbedding = _TE
sys.modules["fastembed"] = fe

# --- stub MinIO storage ---
import app.services.storage as storage_mod
_blobs: dict[str, bytes] = {}
storage_mod.ensure_bucket = lambda: None
storage_mod.put_object = lambda key, data, content_type="": _blobs.__setitem__(key, data)
storage_mod.get_object = lambda key: _blobs[key]

# --- stub Qdrant ---
import app.services.vector_store as vs
import uuid as _uuid
_points: list[dict] = []

vs.ensure_collection = lambda: None

def _upsert(points):
    ids = []
    for p in points:
        pid = str(_uuid.uuid4())
        ids.append(pid)
        _points.append({"id": pid, "vector": p["vector"], "payload": p["payload"]})
    return ids
vs.upsert_chunks = _upsert

def _del_by_doc(doc_id):
    _points[:] = [p for p in _points if p["payload"].get("document_id") != doc_id]
vs.delete_by_document = _del_by_doc

def _del_by_faq(faq_id):
    _points[:] = [p for p in _points if p["payload"].get("faq_id") != faq_id]
vs.delete_by_faq = _del_by_faq

def _del_by_ids(ids):
    s = set(ids)
    _points[:] = [p for p in _points if p["id"] not in s]
vs.delete_by_ids = _del_by_ids

def _cos(a, b):
    s = sum(x*y for x, y in zip(a, b))
    na = sum(x*x for x in a) ** 0.5 or 1
    nb = sum(x*x for x in b) ** 0.5 or 1
    return s/(na*nb)

def _search(vector, tenant_id, industry_codes, top_k=20, knowledge_set_ids=None,
            include_platform=True, kind=None):
    cands = []
    for p in _points:
        pl = p["payload"]
        if pl.get("industry_code") not in industry_codes: continue
        if not pl.get("is_active"): continue
        if kind and pl.get("kind") != kind: continue
        if pl.get("tenant_id") != tenant_id and not (include_platform and pl.get("tenant_id") == 0):
            continue
        if knowledge_set_ids and pl.get("knowledge_set_id") not in knowledge_set_ids:
            continue
        cands.append({"id": p["id"], "score": _cos(vector, p["vector"]), "payload": pl})
    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:top_k]
vs.search = _search

# --- stub LLM ---
import app.services.llm as llm_mod
async def _chat(messages, **kw):
    return "[stub LLM answer]"
async def _stream(messages, **kw):
    for tok in ["[", "stub", " stream", " answer", "]"]:
        yield tok
llm_mod.chat = _chat
llm_mod.chat_stream = _stream

# --- stub redis (in-process) ---
import app.services.cache as cache_mod
class _FakeRedis:
    def __init__(self): self._store = {}; self._sets = {}
    async def set(self, k, v, ex=None): self._store[k] = v
    async def get(self, k): return self._store.get(k)
    async def sadd(self, k, *vs):
        s = self._sets.setdefault(k, set())
        for v in vs: s.add(v.encode() if isinstance(v, str) else v)
    async def smembers(self, k):
        return self._sets.get(k, set())
    async def expire(self, k, ttl): pass
    async def delete(self, k):
        was = k in self._store
        self._store.pop(k, None); self._sets.pop(k, None)
        return 1 if was else 0
_fake = _FakeRedis()
cache_mod._redis = lambda: _fake


from httpx import ASGITransport, AsyncClient
from app.main import app, _bootstrap


async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cli:
        await _bootstrap()
        # login
        r = await cli.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123456"})
        assert r.status_code == 200
        token = r.json()["access_token"]
        H = {"Authorization": f"Bearer {token}"}
        me = (await cli.get("/api/auth/me", headers=H)).json()
        tid = me["tenants"][0]["id"]
        TH = {**H, "X-Tenant-Id": str(tid), "X-Industry": "education"}
        print("✓ login")

        # knowledge set
        ks = (await cli.post("/api/knowledge-sets", headers=TH, json={"name": "test"})).json()["id"]

        # document with multi-paragraph content for chunking
        doc = (await cli.post("/api/documents/manual", headers=TH, json={
            "title": "课程信息",
            "content": "课程时长是 3 个月。\n\n上课时间是每周二、周四。\n\n费用是 2000 元。",
            "knowledge_set_id": ks,
        })).json()
        for _ in range(20):
            d = next(x for x in (await cli.get("/api/documents", headers=TH)).json() if x["id"] == doc["id"])
            if d["status"] in ("published", "failed"): break
            await asyncio.sleep(0.1)
        assert d["status"] == "published"
        print(f"✓ document published, chunks={d['chunk_count']}")

        # list chunks, edit one
        chunks = (await cli.get(f"/api/documents/{doc['id']}/chunks", headers=TH)).json()
        assert len(chunks) >= 1
        c0 = chunks[0]
        r = await cli.patch(f"/api/chunks/{c0['id']}", headers=TH, json={"text": c0["text"] + " 已修改"})
        assert r.status_code == 200
        print("✓ chunk edit (re-embedded)")

        # toggle disable
        r = await cli.post(f"/api/chunks/{c0['id']}/toggle", headers=TH, json={"is_active": False})
        assert r.status_code == 200 and not r.json()["is_active"]
        await cli.post(f"/api/chunks/{c0['id']}/toggle", headers=TH, json={"is_active": True})
        print("✓ chunk toggle")

        # split (only if long enough)
        if len(c0["text"]) > 4:
            r = await cli.post(f"/api/chunks/{c0['id']}/split", headers=TH, json={"position": max(2, len(c0["text"])//2)})
            assert r.status_code == 200
            new_chunks = r.json()
            assert len(new_chunks) == 2
            chunks = (await cli.get(f"/api/documents/{doc['id']}/chunks", headers=TH)).json()
            print(f"✓ chunk split: doc now has {len(chunks)} chunks")

            # merge them back
            ids = [chunks[0]["id"], chunks[1]["id"]]
            r = await cli.post("/api/chunks/merge", headers=TH, json={"chunk_ids": ids})
            assert r.status_code == 200, r.text
            print("✓ chunk merge")

        # FAQ create + index + retrieval
        faq = (await cli.post("/api/faqs", headers=TH, json={
            "question": "课程多长时间？",
            "answer": "我们的课程时长是 3 个月。",
            "similar_questions": ["课时多久", "课程几个月"],
        })).json()
        assert faq["id"]
        print(f"✓ FAQ created id={faq['id']}")

        # debug retrieve - should hit FAQ first since exact-ish match
        r = await cli.post("/api/debug/retrieve", headers=TH, json={"question": "课程多长时间？"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["debug"]["stages"]
        print(f"✓ debug/retrieve: stages={list(body['debug']['stages'].keys())}, "
              f"short_circuit={body['debug']['short_circuit']}")

        # FAQ list
        faqs = (await cli.get("/api/faqs", headers=TH)).json()
        assert any(f["id"] == faq["id"] for f in faqs)
        print(f"✓ FAQ list: {len(faqs)}")

        # FAQ CSV import
        import io
        csv_data = b"question,answer,similar_questions\n\xe4\xb8\x8a\xe8\xaf\xbe\xe6\x97\xb6\xe9\x97\xb4,\xe6\xaf\x8f\xe5\x91\xa8\xe4\xba\x8c\xe5\x9b\x9b,\xe5\x87\xa0\xe7\x82\xb9\xe4\xb8\x8a\xe8\xaf\xbe|\xe4\xbb\x80\xe4\xb9\x88\xe6\x97\xb6\xe5\x80\x99\n"
        files = {"file": ("faqs.csv", io.BytesIO(csv_data), "text/csv")}
        r = await cli.post("/api/faqs/import", headers=TH, files=files)
        assert r.status_code == 200
        assert r.json()["imported"] >= 1
        print(f"✓ FAQ CSV import: {r.json()['imported']}")

        # CSV export
        r = await cli.get("/api/faqs/export.csv", headers=TH)
        assert r.status_code == 200
        assert b"question" in r.content
        print("✓ FAQ CSV export")

        # chat (uses cache + LLM stub)
        r = await cli.post("/api/chat", headers=TH, json={"question": "课程多长时间", "debug": True})
        assert r.status_code == 200, r.text
        body = r.json()
        print(f"✓ chat: source={body['debug']['source']}, answer={body['answer'][:30]!r}")

        # second call - cache hit (same question)
        r = await cli.post("/api/chat", headers=TH, json={"question": "课程多长时间", "debug": True})
        assert r.status_code == 200
        body = r.json()
        print(f"✓ chat #2: source={body['debug']['source']}")

        # clear cache
        r = await cli.delete("/api/chat/cache", headers=TH)
        assert r.status_code == 200
        print(f"✓ cache cleared: {r.json()}")

        # --- unanswered flow ---
        # ask a totally off-topic question -> should be logged as 'miss'
        r = await cli.post("/api/chat", headers=TH, json={
            "question": "明天上海会下雨吗？", "debug": True})
        assert r.status_code == 200
        # list unanswered
        u = (await cli.get("/api/unanswered", headers=TH)).json()
        assert len(u) >= 1
        print(f"✓ unanswered logged: {len(u)} (top category: {u[0]['category']}, status: {u[0]['status']})")
        # stats
        s = (await cli.get("/api/unanswered/stats", headers=TH)).json()
        print(f"✓ stats: total={s['total']} by_status={s['by_status']} by_category={s['by_category']}")
        # convert one to FAQ
        target = u[0]
        r = await cli.post(f"/api/unanswered/{target['id']}/convert-to-faq", headers=TH, json={
            "answer": "我们没有提供天气服务，建议咨询气象部门。",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "handled" and body["handled_faq_id"]
        print(f"✓ converted to FAQ id={body['handled_faq_id']}, status={body['status']}")
        # dismiss another (if exists)
        if len(u) > 1:
            r = await cli.patch(f"/api/unanswered/{u[1]['id']}", headers=TH, json={"status": "dismissed"})
            assert r.status_code == 200
            print(f"✓ dismissed id={u[1]['id']}")

        print("\n🎉 ALL ASSERTIONS PASSED")


asyncio.run(main())
