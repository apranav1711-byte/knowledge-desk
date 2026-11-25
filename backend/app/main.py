"""Knowledge Desk API (runs locally: SQLite database + files in backend/data)."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.v1 import admin, chat, documents, general, session
from app.core.config import settings
from app.core.db import close_pool, init_pool
from app.services.embeddings import get_embedder
from app.services.ingestion import recover_stuck_documents

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("knowledge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    n = await recover_stuck_documents()
    if n:
        log.warning("marked %d interrupted document(s) as failed", n)
    warm = asyncio.create_task(run_in_threadpool(get_embedder))  # load the model now, not on the first upload
    yield
    warm.cancel()
    await close_pool()


app = FastAPI(title=settings.APP_NAME, version="2.0.0", lifespan=lifespan,
              docs_url="/docs" if settings.ENVIRONMENT != "production" else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], max_age=600,
                   allow_private_network=True,  # site is on the internet, API on localhost (Chrome opt-in)
                   allow_headers=["Authorization", "Content-Type"])

PREFIX = "/api/v1"
for r in (general.router, session.router, documents.router, chat.router, admin.router):
    app.include_router(r, prefix=PREFIX)
