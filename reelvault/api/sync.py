"""Sync API used by the Android capture client. Every request needs the pairing token."""
from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import utcnow
from .deps import ws

router = APIRouter(prefix="/api/sync", tags=["sync"])
TOKEN_HEADER = "X-ReelVault-Token"


def require_token(request: Request, x_reelvault_token: str | None = Header(default=None, alias=TOKEN_HEADER)) -> None:
    expected = request.app.state.workspace.db.pairing_token()
    if not x_reelvault_token or not hmac.compare_digest(x_reelvault_token.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid or missing pairing token")


class CaptureIn(BaseModel):
    capture_id: str = Field(min_length=1, max_length=64)
    shared_text: str = Field(default="", max_length=8000)
    url: str | None = Field(default=None, max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    captured_at: str | None = Field(default=None, max_length=40)


class SyncBatch(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    device_name: str = Field(default="", max_length=120)
    captures: list[CaptureIn] = Field(default_factory=list, max_length=200)


@router.get("/ping", dependencies=[Depends(require_token)])
def ping(request: Request) -> dict[str, Any]:
    w = ws(request)
    return {"ok": True, "app": "ReelVault", "version": w.version, "server_name": w.setting("server_name"), "time": utcnow()}


@router.post("/captures", dependencies=[Depends(require_token)])
def receive(batch: SyncBatch, request: Request) -> dict[str, Any]:
    w = ws(request)
    results = w.repo.receive_captures(batch.device_id, batch.device_name, [c.model_dump() for c in batch.captures])
    if w.setting("metadata_auto", True):
        for r in results:
            if r.get("result") == "created" and r.get("idea_id"):
                w.queue_metadata(r["idea_id"])
    return {"ok": True, "results": results, "server_time": utcnow()}
