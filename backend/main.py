"""MultiVera FastAPI application factory."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure parent directory is on path so we can import engine.py etc.
sys.path.insert(0, str(__file__).rsplit("/backend", 1)[0])

from backend.database import engine, Base
from backend.routers import projects, characters, commits, chat, ingestion, export

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("multivera.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    logger.info("Creating database tables if missing...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables ready.")
    yield
    logger.info("Shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="MultiVera API",
        description="Character Context Engine + Interaction Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(characters.router, prefix="/api/v1")
    app.include_router(commits.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(ingestion.router, prefix="/api/v1")
    app.include_router(export.router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "multivera"}

    return app


app = create_app()
