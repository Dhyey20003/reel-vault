"""v2 workspace endpoints: media, import, bulk, covers, notes, tags, trips quick-add, pipeline, repair, local AI, plans."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from ..db import new_id
from ..repo import TAG_SUGGESTIONS
from ..urlnorm import extract_url
from .deps import ws

router = APIRouter(prefix="/api", tags=["v2"])
MEDIA_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska"}
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _404(msg: str = "Not found") -> HTTPException:
    return HTTPException(404, msg)


def _idea_or_404(request: Request, idea_id: str) -> dict[str, Any]:
    idea = ws(request).repo.idea(idea_id)
    if not idea or idea.get("deleted_at"):
        raise _404("Idea not found")
    return idea


# ------------------------------------------------------------------ media
@router.get("/media/{idea_id}")
def media(idea_id: str, request: Request) -> Response:
    """Streams the idea's browser-playable file. Only paths recorded on the idea row are ever served;
    Starlette's FileResponse handles HTTP Range requests for seeking."""
    idea = _idea_or_404(request, idea_id)
    if idea.get("media_status") != "ok" or not idea.get("playback_path"):
        raise HTTPException(409, {"playable": False, "media_status": idea.get("media_status"),
                                  "reason": (idea.get("media") or {}).get("error") or "no browser-playable file for this idea"})
    p = Path(idea["playback_path"])
    if not p.is_file():
        raise HTTPException(409, {"playable": False, "media_status": "missing", "reason": "the playback file is missing"})
    return FileResponse(str(p), media_type=MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"),
                        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"})


@router.get("/ideas/{idea_id}/cover")
def cover(idea_id: str, request: Request) -> Response:
    idea = _idea_or_404(request, idea_id)
    for key in ("cover_path", "thumbnail_path"):
        p = idea.get(key)
        if p and Path(p).is_file():
            return FileResponse(p, media_type=IMAGE_TYPES.get(Path(p).suffix.lower(), "image/jpeg"), headers={"Cache-Control": "private, max-age=3600"})
    raise _404("No cover")


class CoverIn(BaseModel):
    t: float = Field(ge=0)


@router.post("/ideas/{idea_id}/cover/frame")
def cover_from_frame(idea_id: str, body: CoverIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).set_cover(idea_id, t=body.t)
    except KeyError as e:
        raise _404("Idea not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/ideas/{idea_id}/cover/upload")
async def cover_upload(idea_id: str, request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    w = ws(request)
    _idea_or_404(request, idea_id)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_TYPES:
        raise HTTPException(400, "Cover must be PNG, JPG or WEBP")
    data = await file.read()
    if len(data) > 10_000_000:
        raise HTTPException(400, "Cover too large (10 MB max)")
    tmp = w.paths.tmp / f"cover_{new_id()[:8]}{ext}"
    tmp.write_bytes(data)
    try:
        return w.set_cover(idea_id, upload=tmp)
    finally:
        tmp.unlink(missing_ok=True)


@router.post("/ideas/{idea_id}/prepare")
def prepare(idea_id: str, request: Request) -> dict[str, Any]:
    _idea_or_404(request, idea_id)
    return ws(request).prepare_media(idea_id)


@router.post("/ideas/{idea_id}/download/cancel")
def cancel_download(idea_id: str, request: Request) -> dict[str, Any]:
    _idea_or_404(request, idea_id)
    return {"cancelled": ws(request).cancel_download(idea_id)}


@router.post("/ideas/{idea_id}/analyze/cancel")
def cancel_analysis(idea_id: str, request: Request) -> dict[str, Any]:
    _idea_or_404(request, idea_id)
    return {"cancelled": ws(request).cancel_analysis(idea_id)}


# ----------------------------------------------------------- import / bulk
@router.post("/ideas/import", status_code=201)
async def import_local(request: Request, file: UploadFile = File(...), title: str = "") -> dict[str, Any]:
    w = ws(request)
    name = Path(file.filename or "video").name
    if Path(name).suffix.lower() not in MEDIA_TYPES:
        raise HTTPException(400, "Supported video files: mp4, m4v, webm, mov, mkv")
    tmp = w.paths.tmp / f"import_{new_id()[:8]}_{name}"
    with open(tmp, "wb") as f:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    try:
        idea, created = w.import_local(tmp, title=title)
    except ValueError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(409, str(e)) from e
    finally:
        tmp.unlink(missing_ok=True)
    return {"idea": idea, "created": created}


class BulkIn(BaseModel):
    text: str = Field(max_length=200_000)
    allow_duplicate: bool = False


@router.post("/ideas/bulk")
def bulk(body: BulkIn, request: Request) -> dict[str, Any]:
    w = ws(request)
    results = []
    seen: set[str] = set()
    for raw in body.text.splitlines():
        line = raw.strip()
        if not line:
            continue
        url = extract_url(line)
        if not url:
            results.append({"line": line[:120], "result": "invalid", "error": "no http(s) link"}); continue
        if url in seen:
            results.append({"line": line[:120], "result": "duplicate_in_list", "url": url}); continue
        seen.add(url)
        try:
            idea, created = w.repo.create_idea(url, source="manual", allow_duplicate=body.allow_duplicate)
        except ValueError as e:
            results.append({"line": line[:120], "result": "invalid", "error": str(e)}); continue
        if created:
            w.on_capture_synced(idea["id"])
        results.append({"line": line[:120], "result": "created" if created else "duplicate", "idea_id": idea["id"], "url": url})
    return {"results": results, "created": sum(1 for r in results if r["result"] == "created")}


# -------------------------------------------------------------- notes/tags
class NoteIn(BaseModel):
    t: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=2000)


class NotePatch(BaseModel):
    t: float | None = None
    text: str | None = None


@router.post("/ideas/{idea_id}/notes", status_code=201)
def add_note(idea_id: str, body: NoteIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.add_timed_note(idea_id, body.t, body.text)
    except KeyError as e:
        raise _404("Idea not found") from e


@router.put("/notes/{note_id}")
def update_note(note_id: str, body: NotePatch, request: Request) -> dict[str, Any]:
    ws(request).repo.update_timed_note(note_id, body.t, body.text)
    return {"ok": True}


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, request: Request) -> dict[str, Any]:
    ws(request).repo.delete_timed_note(note_id)
    return {"ok": True}


@router.get("/tags")
def tags(request: Request) -> dict[str, Any]:
    return {"tags": ws(request).repo.all_tags(), "suggestions": TAG_SUGGESTIONS}


# ------------------------------------------------------------------ trips
class TripAdd(BaseModel):
    idea_ids: list[str] = Field(min_length=1, max_length=2000)
    trip_id: str | None = None
    new_trip_name: str | None = None


@router.post("/trips/add-ideas")
def add_ideas_to_trip(body: TripAdd, request: Request) -> dict[str, Any]:
    w = ws(request)
    tid = body.trip_id
    if not tid:
        if not body.new_trip_name or not body.new_trip_name.strip():
            raise HTTPException(400, "trip_id or new_trip_name is required")
        tid = w.repo.create_trip(body.new_trip_name)["id"]
    try:
        n = w.repo.add_ideas_to_trip(body.idea_ids, tid)
    except KeyError as e:
        raise _404("Trip not found") from e
    return {"ok": True, "trip_id": tid, "added": n}


@router.delete("/trips/{trip_id}/ideas/{idea_id}")
def remove_from_trip(trip_id: str, idea_id: str, request: Request) -> dict[str, Any]:
    ws(request).repo.remove_idea_from_trip(idea_id, trip_id)
    return {"ok": True}


@router.get("/trips-recent")
def recent_trips(request: Request) -> list[dict[str, Any]]:
    return ws(request).repo.recent_trips()


class AdaptIn(BaseModel):
    idea_ids: list[str] = Field(default_factory=list)
    destination: str = ""
    gear: str = ""
    time_available: str = ""
    preferences: str = ""


@router.post("/trips/{trip_id}/adapt")
def adapt(trip_id: str, body: AdaptIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).adapt_for_trip(trip_id, body.idea_ids, body.destination, body.gear, body.time_available, body.preferences)
    except KeyError as e:
        raise _404("Trip not found") from e


@router.get("/trips/{trip_id}/plans")
def plans(trip_id: str, request: Request) -> list[dict[str, Any]]:
    return ws(request).trip_plans(trip_id)


class PlanIn(BaseModel):
    plan: dict[str, Any]


@router.put("/plans/{plan_id}")
def save_plan(plan_id: str, body: PlanIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).save_plan(plan_id, body.plan)
    except Exception as e:  # pydantic
        raise HTTPException(400, f"Plan did not validate: {str(e)[:300]}") from e


# --------------------------------------------------------- pipeline/repair
@router.get("/pipeline")
def pipeline(request: Request) -> dict[str, Any]:
    return ws(request).pipeline_status()


@router.post("/pipeline/resume")
def pipeline_resume(request: Request) -> dict[str, Any]:
    w = ws(request)
    w.db.set_setting("pipeline_paused", False)
    return {"ok": True, "resumed": w.resume_pipeline()}


@router.post("/pipeline/pause")
def pipeline_pause(request: Request) -> dict[str, Any]:
    ws(request).db.set_setting("pipeline_paused", True)
    return {"ok": True}


@router.get("/repair")
def repair(request: Request) -> dict[str, Any]:
    return ws(request).repair_scan()


@router.get("/diagnostics")
def diagnostics(request: Request) -> JSONResponse:
    return JSONResponse(ws(request).diagnostics(), headers={"Content-Disposition": 'attachment; filename="reelvault-diagnostics.json"'})


@router.get("/ai/local")
def ai_local(request: Request) -> dict[str, Any]:
    w = ws(request)
    from ..services import local_ai
    hw = local_ai.hardware()
    return {"status": w.ai_status(), "hardware": hw, "recommended": local_ai.recommend_model(hw.get("ram_gb")), "choices": local_ai.MODEL_CHOICES}


@router.post("/ai/local/test")
def ai_local_test(request: Request) -> dict[str, Any]:
    return ws(request).test_local_ai()


@router.get("/lan")
def lan(request: Request) -> dict[str, Any]:
    return ws(request).lan_info()
