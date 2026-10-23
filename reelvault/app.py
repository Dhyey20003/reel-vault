"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import sync, v2, workspace as workspace_api
from .config import static_dir
from .netutil import is_private_client
from .workspace import Workspace

log = logging.getLogger("reelvault.app")


def create_app(data_dir: Path, *, port: int = 8765, lan_enabled: bool = False, workspace: Workspace | None = None) -> FastAPI:
    ws = workspace or Workspace(data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resumed = ws.resume_pipeline()
        if any(resumed.values()):
            log.info("resumed background work after restart: %s", resumed)
        yield
        ws.close()

    app = FastAPI(title="ReelVault", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.workspace = ws
    app.state.port = port
    app.state.lan_enabled = lan_enabled

    @app.middleware("http")
    async def private_network_only(request: Request, call_next: Any):
        client = request.client.host if request.client else None
        # Starlette's TestClient reports the pseudo host "testclient"; real servers always give an IP.
        if client not in (None, "testclient") and not is_private_client(client):
            return JSONResponse({"detail": "ReelVault only accepts connections from private networks"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(sync.router)
    app.include_router(workspace_api.router)
    app.include_router(v2.router)

    static = static_dir()
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    return app
