"""Workspace API consumed by the local web UI (localhost; no token needed, LAN clients only
reach it from private addresses when LAN access is enabled)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from ..config import DOWNLOAD_STATUSES, SETTING_DEFAULTS, STATUSES
from ..netutil import lan_ip
from ..repo import ConflictError
from ..services import export as export_svc, resolve
from ..services.analysis import brief_to_markdown
from ..services.reminders import due_ideas, mark_reminded
from ..urlnorm import extract_url, normalize_url
from .deps import ws

router = APIRouter(prefix="/api", tags=["workspace"])


def _404(msg: str = "Not found") -> HTTPException:
    return HTTPException(status_code=404, detail=msg)


# ------------------------------------------------------------------ status
@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    w = ws(request)
    s = w.status()
    s["lan_ip"] = lan_ip()
    s["port"] = request.app.state.port
    s["lan_enabled_running"] = request.app.state.lan_enabled
    s["statuses"] = STATUSES
    s["priorities"] = w.setting("priorities")
    s["download_statuses"] = DOWNLOAD_STATUSES
    return s


# ---------------------------------------------------------------- settings
class SettingsIn(BaseModel):
    values: dict[str, Any]


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    w = ws(request)
    return {"settings": w.db.all_settings(), "defaults": SETTING_DEFAULTS,
            "restart_required_keys": ["lan_enabled", "port"]}


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request) -> dict[str, Any]:
    w = ws(request)
    for key, value in body.values.items():
        if key not in SETTING_DEFAULTS:
            raise HTTPException(400, f"Unknown setting '{key}'")
        if key == "port" and not (1024 <= int(value) <= 65535):
            raise HTTPException(400, "Port must be between 1024 and 65535")
        if key == "priorities" and (not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value)):
            raise HTTPException(400, "Priorities must be a list of names")
        if key == "media_dir" and value:
            p = Path(str(value))
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise HTTPException(400, f"Cannot use that media folder: {e}") from e
        w.db.set_setting(key, value)
    return get_settings(request)


@router.get("/pairing")
def pairing(request: Request) -> dict[str, Any]:
    w = ws(request)
    import segno
    from urllib.parse import quote
    info = w.lan_info()
    ip = info["advertised_host"]
    port = request.app.state.port
    token = w.db.pairing_token()
    warnings = []
    if not ip:
        warnings.append("No private LAN address found on this computer. Connect to WiFi/Ethernet, or type the address under Advertised host.")
        ip = "127.0.0.1"
    if not request.app.state.lan_enabled:
        warnings.append("LAN access is OFF: the phone cannot connect until you enable it in Settings and restart ReelVault.")
    chosen = next((c for c in info["candidates"] if c["ip"] == ip), None)
    if chosen and chosen.get("virtual"):
        warnings.append(f"{ip} looks like a virtual/VPN adapter ({chosen['reason']}); pick your WiFi address under Advertised host.")
    uri = f"reelvault://pair?host={quote(ip)}&port={port}&token={quote(token, safe='')}"
    svg = segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#111", light=None)
    return {"host": ip, "port": port, "token": token, "uri": uri, "qr_svg": svg, "warnings": warnings,
            "candidates": info["candidates"], "lan_enabled_running": request.app.state.lan_enabled}


@router.post("/pairing/rotate")
def rotate(request: Request) -> dict[str, Any]:
    ws(request).db.rotate_pairing_token()
    return pairing(request)


@router.get("/devices")
def devices(request: Request) -> list[dict[str, Any]]:
    return ws(request).repo.devices()


# -------------------------------------------------------------- categories
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.get("/categories")
def categories(request: Request) -> list[dict[str, Any]]:
    return ws(request).repo.categories()


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.create_category(body.name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/categories/{cid}")
def rename_category(cid: str, body: CategoryIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.rename_category(cid, body.name)
    except KeyError as e:
        raise _404("Category not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/categories/{cid}")
def delete_category(cid: str, request: Request, reassign_to: str | None = None) -> dict[str, Any]:
    w = ws(request)
    if not w.repo.category(cid):
        raise _404("Category not found")
    try:
        moved = w.repo.delete_category(cid, reassign_to or None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "reassigned": moved}


# ------------------------------------------------------------------- ideas
class IdeaCreate(BaseModel):
    url: str = Field(min_length=1, max_length=4000)
    title: str | None = None
    notes: str | None = None
    allow_duplicate: bool = False


class IdeaUpdate(BaseModel):
    fields: dict[str, Any]
    expected_updated_at: str | None = None


@router.get("/ideas")
def list_ideas(request: Request, q: str = "", status: str | None = None, priority: str | None = None,
               category_id: str | None = None, trip_id: str | None = None, inbox: bool = False,
               download_status: str | None = None, captured_from: str | None = None, captured_to: str | None = None,
               sort: str = "captured_at", order: str = "desc", limit: int = Query(500, le=2000), offset: int = 0,
               tag: str | None = None, playable: bool = False) -> dict[str, Any]:
    w = ws(request)
    items = w.repo.list_ideas(q=q, status=status, priority=priority, category_id=category_id, trip_id=trip_id, inbox=inbox,
                              download_status=download_status, captured_from=captured_from, captured_to=captured_to,
                              sort=sort, order=order, limit=limit, offset=offset, tag=tag, playable=playable)
    return {"items": items, "count": len(items), "counts": w.repo.counts()}


@router.post("/ideas", status_code=201)
def create_idea(body: IdeaCreate, request: Request) -> dict[str, Any]:
    w = ws(request)
    url = extract_url(body.url) or body.url.strip()
    try:
        idea, created = w.repo.create_idea(url, shared_text=body.url if url != body.url.strip() else None,
                                           source="manual", title=body.title, notes=body.notes,
                                           allow_duplicate=body.allow_duplicate)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if created:
        w.on_capture_synced(idea["id"])
    return {"idea": idea, "created": created}


@router.get("/ideas/{idea_id}")
def get_idea(idea_id: str, request: Request) -> dict[str, Any]:
    w = ws(request)
    idea = w.repo.idea(idea_id)
    if not idea or idea.get("deleted_at"):
        raise _404("Idea not found")
    idea["jobs"] = w.jobs_for(idea_id)
    return idea


@router.put("/ideas/{idea_id}")
def update_idea(idea_id: str, body: IdeaUpdate, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.update_idea(idea_id, body.fields, expected_updated_at=body.expected_updated_at)
    except KeyError as e:
        raise _404("Idea not found") from e
    except ConflictError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/ideas/{idea_id}")
def delete_idea(idea_id: str, request: Request) -> dict[str, Any]:
    w = ws(request)
    if not w.repo.idea(idea_id):
        raise _404("Idea not found")
    w.repo.delete_idea(idea_id)
    return {"ok": True}


class TripAssign(BaseModel):
    trip_ids: list[str]


@router.put("/ideas/{idea_id}/trips")
def assign_trips(idea_id: str, body: TripAssign, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.set_idea_trips(idea_id, body.trip_ids)
    except KeyError as e:
        raise _404("Idea not found") from e


@router.post("/ideas/{idea_id}/metadata/retry")
def retry_metadata(idea_id: str, request: Request) -> dict[str, Any]:
    w = ws(request)
    if not w.repo.idea(idea_id):
        raise _404("Idea not found")
    return {"queued": w.queue_metadata(idea_id, force=True)}


@router.post("/ideas/{idea_id}/download")
def download(idea_id: str, request: Request) -> dict[str, Any]:
    try:
        return ws(request).queue_download(idea_id)
    except KeyError as e:
        raise _404("Idea not found") from e


@router.post("/ideas/{idea_id}/download/verify")
def verify_download(idea_id: str, request: Request) -> dict[str, Any]:
    try:
        return ws(request).verify_download(idea_id)
    except KeyError as e:
        raise _404("Idea not found") from e


@router.post("/ideas/{idea_id}/analyze")
def analyze(idea_id: str, request: Request, force: bool = False) -> dict[str, Any]:
    try:
        return ws(request).queue_analysis(idea_id, force=force)
    except KeyError as e:
        raise _404("Idea not found") from e


class BriefIn(BaseModel):
    brief: dict[str, Any]


@router.put("/ideas/{idea_id}/analysis")
def save_analysis(idea_id: str, body: BriefIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).save_edited_analysis(idea_id, body.brief)
    except KeyError as e:
        raise _404("Idea not found") from e
    except Exception as e:  # pydantic ValidationError
        raise HTTPException(400, f"Brief did not validate: {str(e)[:300]}") from e


@router.get("/ideas/{idea_id}/analysis.md", response_class=PlainTextResponse)
def analysis_markdown(idea_id: str, request: Request) -> str:
    idea = ws(request).repo.idea(idea_id)
    if not idea or not idea.get("analysis"):
        raise _404("No analysis for this idea")
    return brief_to_markdown(idea["analysis"]["brief"], idea.get("title") or "")


@router.get("/ideas/{idea_id}/thumbnail")
def thumbnail(idea_id: str, request: Request) -> Response:
    idea = ws(request).repo.idea(idea_id)
    if not idea:
        raise _404("Idea not found")
    for key in ("cover_path", "thumbnail_path"):
        if idea.get(key) and Path(idea[key]).is_file():
            return FileResponse(idea[key])
    raise _404("No thumbnail")


@router.post("/ideas/{idea_id}/attachments", status_code=201)
async def upload_attachment(idea_id: str, request: Request, file: UploadFile = File(...), kind: str = "screenshot") -> dict[str, Any]:
    w = ws(request)
    if not w.repo.idea(idea_id):
        raise _404("Idea not found")
    if kind not in ("screenshot", "other"):
        raise HTTPException(400, "kind must be screenshot or other")
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if kind == "screenshot" and ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Screenshots must be PNG, JPG or WEBP")
    data = await file.read()
    if len(data) > 20_000_000:
        raise HTTPException(400, "File too large (20 MB max)")
    folder = w.paths.attachments / idea_id
    folder.mkdir(parents=True, exist_ok=True)
    from ..db import new_id
    dest = folder / f"{new_id()[:8]}_{name}"
    dest.write_bytes(data)
    return w.repo.add_attachment(idea_id, kind, name, str(dest))


@router.get("/attachments/{att_id}")
def get_attachment(att_id: str, request: Request) -> Response:
    att = ws(request).repo.attachment(att_id)
    if not att or not Path(att["path"]).is_file():
        raise _404("Attachment not found")
    return FileResponse(att["path"], filename=att["filename"])


@router.delete("/attachments/{att_id}")
def delete_attachment(att_id: str, request: Request) -> dict[str, Any]:
    w = ws(request)
    att = w.repo.attachment(att_id)
    if not att:
        raise _404("Attachment not found")
    try:
        Path(att["path"]).unlink(missing_ok=True)
    except OSError:
        pass
    w.repo.delete_attachment(att_id)
    return {"ok": True}


# ---------------------------------------------------------- local file actions
def _local_file(request: Request, idea_id: str) -> Path:
    idea = ws(request).repo.idea(idea_id)
    if not idea:
        raise _404("Idea not found")
    lp = idea.get("local_path")
    if not lp or not Path(lp).is_file():
        raise HTTPException(409, "No local reference file for this idea")
    return Path(lp)


def _only_windows_or_desktop() -> None:
    if os.name != "nt" and sys.platform != "darwin" and not shutil.which("xdg-open"):
        raise HTTPException(501, "Opening files is only supported on the desktop OS running ReelVault")


@router.post("/ideas/{idea_id}/open")
def open_local(idea_id: str, request: Request) -> dict[str, Any]:
    path = _local_file(request, idea_id)
    _only_windows_or_desktop()
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
    return {"ok": True}


@router.post("/ideas/{idea_id}/reveal")
def reveal_local(idea_id: str, request: Request) -> dict[str, Any]:
    path = _local_file(request, idea_id)
    _only_windows_or_desktop()
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603,S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])  # noqa: S603,S607
    return {"ok": True}


@router.post("/open-folder")
def open_folder(request: Request, which: str = "media") -> dict[str, Any]:
    w = ws(request)
    folder = {"media": w.media_dir(), "data": w.paths.data_dir, "exports": w.paths.exports}.get(which)
    if folder is None:
        raise HTTPException(400, "which must be media, data or exports")
    folder.mkdir(parents=True, exist_ok=True)
    _only_windows_or_desktop()
    if os.name == "nt":
        os.startfile(str(folder))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
    return {"ok": True, "path": str(folder)}


# ------------------------------------------------------------------- trips
class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    location: str = ""
    start_date: str | None = None
    end_date: str | None = None
    notes: str = ""
    checklist: list[dict[str, Any]] = Field(default_factory=list)


class TripPatch(BaseModel):
    fields: dict[str, Any]


@router.get("/trips")
def trips(request: Request, include_archived: bool = False) -> list[dict[str, Any]]:
    return ws(request).repo.trips(include_archived=include_archived)


@router.post("/trips", status_code=201)
def create_trip(body: TripIn, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.create_trip(**body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/trips/{trip_id}")
def get_trip(trip_id: str, request: Request) -> dict[str, Any]:
    t = ws(request).repo.trip(trip_id)
    if not t:
        raise _404("Trip not found")
    return t


@router.put("/trips/{trip_id}")
def update_trip(trip_id: str, body: TripPatch, request: Request) -> dict[str, Any]:
    try:
        return ws(request).repo.update_trip(trip_id, body.fields)
    except KeyError as e:
        raise _404("Trip not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/trips/{trip_id}")
def delete_trip(trip_id: str, request: Request) -> dict[str, Any]:
    w = ws(request)
    if not w.repo.trip(trip_id):
        raise _404("Trip not found")
    w.repo.delete_trip(trip_id)
    return {"ok": True}


@router.get("/trips/{trip_id}/suggestions")
def trip_suggestions(trip_id: str, request: Request) -> list[dict[str, Any]]:
    """Ideas in the inbox whose text mentions the trip name or location. Suggestions only; nothing is assigned."""
    w = ws(request)
    t = w.repo.trip(trip_id)
    if not t:
        raise _404("Trip not found")
    terms = [x.strip().lower() for x in (t["name"], t.get("location") or "") if x and x.strip()]
    out = []
    for idea in w.repo.list_ideas(inbox=True, limit=2000):
        hay = " ".join(str(idea.get(k) or "") for k in ("title", "caption", "notes", "shared_text")).lower()
        if any(term in hay for term in terms):
            out.append({"id": idea["id"], "title": idea.get("title"), "original_url": idea["original_url"]})
    return out


@router.post("/trips/{trip_id}/export")
def export_trip(trip_id: str, request: Request, copy_media: bool = True) -> dict[str, Any]:
    w = ws(request)
    t = w.repo.trip(trip_id)
    if not t:
        raise _404("Trip not found")
    ideas = t.pop("ideas")
    folder = export_svc.export_trip(t, ideas, w.paths.exports, copy_media=copy_media)
    return {"ok": True, "folder": str(folder)}


@router.post("/trips/{trip_id}/resolve-import")
def resolve_import(trip_id: str, request: Request) -> dict[str, Any]:
    w = ws(request)
    t = w.repo.trip(trip_id)
    if not t:
        raise _404("Trip not found")
    files = [i["local_path"] for i in t["ideas"] if i.get("local_path")]
    return resolve.import_to_media_pool(files, t["name"], w.setting("resolve_scripting_path") or "")


class ShotListIn(BaseModel):
    idea_ids: list[str]
    format: str = "md"
    heading: str = "Shot list"


@router.post("/exports/shotlist", response_class=PlainTextResponse)
def shot_list(body: ShotListIn, request: Request) -> PlainTextResponse:
    w = ws(request)
    ideas = [i for i in (w.repo.idea(x) for x in body.idea_ids) if i]
    fmt = "md" if body.format == "md" else "txt"
    text = export_svc.shot_list_document(ideas, fmt, body.heading)
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="shotlist.{fmt}"'})


# --------------------------------------------------------------- reminders
@router.get("/reminders/due")
def reminders_due(request: Request) -> dict[str, Any]:
    w = ws(request)
    if not w.setting("reminders_enabled", False):
        return {"enabled": False, "due": []}
    return {"enabled": True, "due": due_ideas(w.db, int(w.setting("reminder_quiet_hours") or 24))}


class AckIn(BaseModel):
    idea_ids: list[str]


@router.post("/reminders/ack")
def reminders_ack(body: AckIn, request: Request) -> dict[str, Any]:
    mark_reminded(ws(request).db, body.idea_ids)
    return {"ok": True}


# ------------------------------------------------------------------- utils
@router.get("/util/normalize")
def util_normalize(url: str) -> dict[str, Any]:
    u = extract_url(url) or url
    return {"input": url, "url": u, "normalized": normalize_url(u)}


@router.post("/backup")
def backup(request: Request) -> dict[str, Any]:
    w = ws(request)
    import sqlite3
    from datetime import datetime
    dest = w.paths.backups / f"reelvault-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    src = w.db.connection()
    out = sqlite3.connect(str(dest))
    try:
        src.backup(out)
    finally:
        out.close()
    return {"ok": True, "path": str(dest)}
