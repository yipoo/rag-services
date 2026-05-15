from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select

from app.core.limiter import limiter

from app.api import admin, auth, chat, chunks, debug, documents, faqs, industries, knowledge_sets, unanswered
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.safety import run_startup_checks
from app.core.security import hash_password
from app.models import Industry, Tenant, TenantIndustrySubscription, TenantMember, User
from app.services import storage, vector_store

log = structlog.get_logger()


async def _bootstrap() -> None:
    """Create tables, seed platform admin, default industries, demo tenant."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        # platform admin
        admin_user = (await db.execute(
            select(User).where(User.email == settings.BOOTSTRAP_ADMIN_EMAIL)
        )).scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                email=settings.BOOTSTRAP_ADMIN_EMAIL,
                hashed_password=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
                name="Platform Admin",
                is_platform_admin=True,
            )
            db.add(admin_user)
            await db.flush()
            log.info("bootstrap.admin_created", email=admin_user.email)

        # seed industries
        seeds = [
            ("general", "通用", "通用客服话术"),
            ("education", "教育", "教育培训行业"),
            ("catering", "餐饮", "餐饮行业"),
            ("drycleaning", "干洗", "干洗洗护行业"),
        ]
        for code, name, desc in seeds:
            ex = (await db.execute(select(Industry).where(Industry.code == code))).scalar_one_or_none()
            if not ex:
                db.add(Industry(code=code, name=name, description=desc))

        # demo tenant
        demo = (await db.execute(select(Tenant).where(Tenant.code == "demo"))).scalar_one_or_none()
        if not demo:
            demo = Tenant(code="demo", name="演示租户", plan="basic", default_industry_code="general")
            db.add(demo)
            await db.flush()
            for code in ["general", "education", "catering"]:
                db.add(TenantIndustrySubscription(tenant_id=demo.id, industry_code=code))
            db.add(TenantMember(tenant_id=demo.id, user_id=admin_user.id, role="admin"))

        await db.commit()

    # ensure infra
    try:
        storage.ensure_bucket()
    except Exception as e:
        log.warning("bootstrap.minio_unavailable", error=str(e))
    try:
        vector_store.ensure_collection()
    except Exception as e:
        log.warning("bootstrap.qdrant_unavailable", error=str(e))

    # warm up embedding model so first chat request doesn't pay cold start
    try:
        from app.services import embeddings
        import asyncio as _aio
        async def _warm():
            await _aio.to_thread(embeddings.embed_one, "warmup")
            log.info("embedding.warmed")
        _aio.create_task(_warm())
    except Exception as e:
        log.warning("bootstrap.embedding_warmup_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_checks()
    await _bootstrap()
    yield


app = FastAPI(title="RAG Services", version="0.1.0", lifespan=lifespan)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=_origins != ["*"],  # credentials are incompatible with wildcard
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(industries.router)
app.include_router(knowledge_sets.router)
app.include_router(documents.router)
app.include_router(chunks.router)
app.include_router(faqs.router)
app.include_router(chat.router)
app.include_router(debug.router)
app.include_router(unanswered.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
