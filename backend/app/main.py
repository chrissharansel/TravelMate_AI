import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import copilot_service as cs
from .config import get_settings
from .db import close_db, ensure_indexes
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("travelmate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_indexes()
    except Exception as e:
        log.error("MongoDB index setup failed: %s", e)
    try:
        import asyncio
        from .knowledge import rag
        n = await asyncio.to_thread(rag.build_index)
        log.info("Knowledge base ready (%s documents)", n)
    except Exception as e:
        log.error("RAG index failed (first run downloads the embedding model, needs internet): %s", e)
    yield
    await cs.stop_copilot()
    await close_db()


app = FastAPI(title="TravelMate AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_url, "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
