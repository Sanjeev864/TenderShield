"""TenderShield Nexus backend - FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000   (from backend/)
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api.restructuring_routes import router as restructuring_router
from .api.routes import router
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    yield


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built dashboard from the API origin, falling back to index.html for client-side routes."""
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(
        title="TenderShield Nexus API",
        version="0.1.0",
        description="SDG 9.3 procurement restructuring & supplier intelligence (primary), and explainable tender "
                    "assurance (secondary): rule extraction, compliance, relationship graph, bid intelligence, evidence reasoning, "
                    "counterfactual robustness, "
                    "human disposition and evidence integrity.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(restructuring_router)
    # TS_STATIC_DIR points at frontend/dist in the single-container deployment.
    static_dir = os.environ.get("TS_STATIC_DIR")
    if static_dir and (Path(static_dir) / "index.html").is_file():
        _mount_frontend(app, Path(static_dir))
    return app


app = create_app()
