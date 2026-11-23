"""Knowledge Desk API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, chat, documents, general
from app.core.config import settings
from app.core.db import close_pool, init_pool
from app.services.ingestion import recover_stuck_documents

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("knowledge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.supabase_configured:
        await init_pool()
        n = await recover_stuck_documents()
        if n:
            log.warning("marked %d interrupted document(s) as failed", n)
    else:
        log.warning("Supabase is not configured: set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and DATABASE_URL")
    yield
    await close_pool()


app = FastAPI(title=settings.APP_NAME, version="2.0.0", lifespan=lifespan,
              docs_url="/docs" if settings.ENVIRONMENT != "production" else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

PREFIX = "/api/v1"
for r in (general.router, documents.router, chat.router, admin.router):
    app.include_router(r, prefix=PREFIX)
