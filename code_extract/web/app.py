"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from code_extract.web.api import router
from code_extract.web.api_analysis import router as analysis_router
from code_extract.web.api_catalog import router as catalog_router
from code_extract.web.api_diff import router as diff_router
from code_extract.web.api_docs import router as docs_router
from code_extract.web.api_tour import router as tour_router
from code_extract.web.api_tools import router as tools_router
from code_extract.web.api_remix import router as remix_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="code-extract", version="0.3.0")

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Core API
    app.include_router(router)

    # v0.3 analysis routers
    app.include_router(analysis_router)
    app.include_router(catalog_router)
    app.include_router(diff_router)
    app.include_router(docs_router)
    app.include_router(tour_router)
    app.include_router(tools_router)
    app.include_router(remix_router)

    # Static files (must be last — catches all unmatched routes)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


app = create_app()
