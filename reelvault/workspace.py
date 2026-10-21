"""The Workspace wires storage, settings and background work together."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from . import __version__
from .config import Paths, default_media_dir, get_ai_api_key
from .db import Database, new_id, utcnow
from .repo import Repo
from .services import analysis as analysis_svc
from .services import downloader, frames, metadata as metadata_svc, resolve, tools
from .services.jobs import JobRunner

log = logging.getLogger("reelvault.workspace")


class Workspace:
    def __init__(self, data_dir: Path, *, workers: int = 3):
        self.paths = Paths(data_dir)
        self.paths.ensure()
        self.db = Database(self.paths.db_path)
        self.applied_migrations = self.db.migrate()
        self.repo = Repo(self.db)
        self.jobs = JobRunner(workers=workers)
        self.version = __version__

    def close(self) -> None:
        self.jobs.shutdown()
        self.db.close()

    # ---------------------------------------------------------------- settings
    def setting(self, key: str, default: Any = None) -> Any:
        return self.db.get_setting(key, default)

    def media_dir(self) -> Path:
        raw = self.setting("media_dir") or ""
        return Path(raw) if raw else default_media_dir()

    def tools(self) -> dict[str, Any]:
        return tools.detect_tools(self.setting("ytdlp_path") or "", self.setting("ffmpeg_path") or "")

    def ai_status(self) -> dict[str, Any]:
        provider = self.setting("ai_provider") or "anthropic"
        key = get_ai_api_key(self.paths, provider)
        return {"provider": provider, "model": self.setting("ai_model"), "configured": bool(key),
                "key_source": "environment or config.json" if key else None,
                "how_to_configure": "Set REELVAULT_AI_API_KEY (or ANTHROPIC_API_KEY) as an environment variable, or create "
                                    f"{self.paths.config_file} containing {{\"ai_api_key\": \"sk-...\"}} and restart."}

    def status(self) -> dict[str, Any]:
        return {"version": self.version, "data_dir": str(self.paths.data_dir), "media_dir": str(self.media_dir()),
                "db_path": str(self.paths.db_path), "schema_version": self.db.current_version(),
                "tools": self.tools(), "ai": self.ai_status(), "resolve": resolve.detect(self.setting("resolve_scripting_path") or ""),
                "counts": self.repo.counts()}

    # ---------------------------------------------------------------- metadata
    def queue_metadata(self, idea_id: str, force: bool = False) -> bool:
        idea = self.repo.idea(idea_id)
        if not idea:
            return False
        if not force and idea["metadata_status"] == "ok":
            return False
        self.repo.set_internal(idea_id, metadata_status="fetching", metadata_error=None)
        return self.jobs.submit(f"metadata:{idea_id}", lambda: self._fetch_metadata(idea_id))

    def _fetch_metadata(self, idea_id: str) -> None:
        idea = self.repo.idea(idea_id)
        if not idea:
            return
        t = self.tools()
        providers = metadata_svc.build_providers(self.setting("metadata_providers") or ["ytdlp", "oembed"],
                                                t["ytdlp"]["path"], self.setting("instagram_oembed_token") or "")
        md, errors = metadata_svc.fetch_metadata(idea["original_url"], providers)
        if md is None:
            self.repo.set_internal(idea_id, metadata_status="unavailable",
                                   metadata_error="; ".join(errors)[:500] or "no provider could retrieve metadata")
            log.info("metadata unavailable for %s: %s", idea_id, errors)
            return
        fields: dict[str, Any] = {"metadata_status": "ok", "metadata_error": None, "metadata_provider": md.provider,
                                  "metadata_json": _json(md.raw)}
        # Never overwrite what the user typed; only fill blanks.
        fresh = self.repo.idea(idea_id) or idea
        if md.title and not fresh["title"]:
            fields["title"] = md.title
        if md.creator and not fresh["creator"]:
            fields["creator"] = md.creator
        if md.caption and not fresh["caption"]:
            fields["caption"] = md.caption
        if md.canonical_url and not fresh["canonical_url"]:
            fields["canonical_url"] = md.canonical_url
        if md.thumbnail_url:
            fields["thumbnail_url"] = md.thumbnail_url
            try:
                dest = metadata_svc.download_file(md.thumbnail_url, self.paths.thumbnails / idea_id)
                fields["thumbnail_path"] = str(dest)
            except Exception as e:  # noqa: BLE001
                log.info("thumbnail download failed for %s: %s", idea_id, e)
        self.repo.set_internal(idea_id, **fields)

    # ---------------------------------------------------------------- download
    def queue_download(self, idea_id: str) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        t = self.tools()
        if not t["ytdlp"]["found"]:
            return {"ok": False, "error": "yt-dlp is not installed. " + t["ytdlp"]["install_hint"]}
        if idea["download_status"] in ("queued", "downloading") and self.jobs.is_running(f"download:{idea_id}"):
            return {"ok": True, "job_id": None, "note": "already in progress"}
        job_id = new_id()
        with self.db.tx() as conn:
            conn.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES (?,?,?,?)",
                         (job_id, idea_id, "queued", utcnow()))
        self.repo.set_internal(idea_id, download_status="queued", download_error=None)
        self.jobs.submit(f"download:{idea_id}", lambda: self._run_download(job_id, idea_id, t))
        return {"ok": True, "job_id": job_id}

    def _download_target(self, idea: dict[str, Any]) -> Path:
        trip = idea["trips"][0]["name"] if idea.get("trips") else "General"
        return self.media_dir() / downloader.safe_folder_name(trip)

    def _run_download(self, job_id: str, idea_id: str, t: dict[str, Any]) -> None:
        idea = self.repo.idea(idea_id)
        if not idea:
            return
        self._job_update("download_jobs", job_id, status="downloading", started_at=utcnow())
        self.repo.set_internal(idea_id, download_status="downloading")
        last = {"p": 0.0}

        def progress(p: float, line: str) -> None:
            if p - last["p"] >= 2 or p >= 100:
                last["p"] = p
                self._job_update("download_jobs", job_id, progress=p)
        try:
            out = downloader.run_download(ytdlp_path=t["ytdlp"]["path"], ffmpeg_path=t["ffmpeg"]["path"],
                                          url=idea["canonical_url"] or idea["original_url"],
                                          target_dir=self._download_target(idea), idea_id=idea_id, on_progress=progress)
        except downloader.DownloadError as e:
            self._job_update("download_jobs", job_id, status="failed", error=str(e), finished_at=utcnow())
            self.repo.set_internal(idea_id, download_status="failed", download_error=str(e))
            return
        self._job_update("download_jobs", job_id, status="downloaded", progress=100.0, output_path=str(out), finished_at=utcnow())
        self.repo.set_internal(idea_id, download_status="downloaded", download_error=None, local_path=str(out))

    def verify_download(self, idea_id: str) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        lp = idea.get("local_path")
        exists = bool(lp) and Path(lp).is_file() and Path(lp).stat().st_size > 0
        if idea["download_status"] == "downloaded" and not exists:
            self.repo.set_internal(idea_id, download_status="not_downloaded", local_path=None,
                                   download_error="The local file is missing; download again")
        return {"exists": exists, "path": lp}

    def _job_update(self, table: str, job_id: str, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.db.tx() as conn:
            conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), job_id))

    def jobs_for(self, idea_id: str) -> dict[str, Any]:
        conn = self.db.connection()
        d = conn.execute("SELECT * FROM download_jobs WHERE idea_id=? ORDER BY created_at DESC LIMIT 1", (idea_id,)).fetchone()
        a = conn.execute("SELECT * FROM analysis_jobs WHERE idea_id=? ORDER BY created_at DESC LIMIT 1", (idea_id,)).fetchone()
        return {"download": dict(d) if d else None, "analysis": dict(a) if a else None}

    # ---------------------------------------------------------------- analysis
    def queue_analysis(self, idea_id: str) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        provider_name = self.setting("ai_provider") or "anthropic"
        key = get_ai_api_key(self.paths, provider_name)
        try:
            provider = analysis_svc.build_provider(provider_name, key)
        except analysis_svc.NotConfigured as e:
            return {"ok": False, "error": str(e), "configured": False}
        if self.jobs.is_running(f"analysis:{idea_id}"):
            return {"ok": True, "note": "already running"}
        model = self.setting("ai_model") or "claude-opus-5-5"
        job_id = new_id()
        with self.db.tx() as conn:
            conn.execute("INSERT INTO analysis_jobs(id, idea_id, status, provider, model, created_at) VALUES (?,?,?,?,?,?)",
                         (job_id, idea_id, "queued", provider_name, model, utcnow()))
        self.repo.set_internal(idea_id, analysis_status="queued", analysis_error=None)
        self.jobs.submit(f"analysis:{idea_id}", lambda: self._run_analysis(job_id, idea_id, provider, model))
        return {"ok": True, "job_id": job_id}

    def _run_analysis(self, job_id: str, idea_id: str, provider: analysis_svc.AnalysisProvider, model: str) -> None:
        idea = self.repo.idea(idea_id)
        if not idea:
            return
        self._job_update("analysis_jobs", job_id, status="running", started_at=utcnow())
        self.repo.set_internal(idea_id, analysis_status="running")
        frame_paths: list[Path] = []
        t = self.tools()
        n_frames = int(self.setting("ai_frames") or 0)
        if idea.get("local_path") and Path(idea["local_path"]).is_file() and t["ffmpeg"]["found"] and n_frames > 0:
            frame_dir = self.paths.tmp / "frames" / idea_id
            shutil.rmtree(frame_dir, ignore_errors=True)
            frame_paths = frames.extract_frames(t["ffmpeg"]["path"], t["ffprobe"]["path"], Path(idea["local_path"]), frame_dir, n_frames)
        shots = [Path(a["path"]) for a in self._attachments(idea_id) if a["kind"] == "screenshot" and Path(a["path"]).is_file()]
        inputs = analysis_svc.AnalysisInputs(url=idea["canonical_url"] or idea["original_url"], title=idea["title"],
                                             creator=idea["creator"], caption=idea["caption"], notes=idea["notes"],
                                             transcript=idea["transcript"], frames=frame_paths, screenshots=shots)
        self._job_update("analysis_jobs", job_id, inputs_json=_json(inputs.summary()))
        try:
            brief, usage = provider.analyze(inputs, model)
        except analysis_svc.AnalysisError as e:
            self._job_update("analysis_jobs", job_id, status="failed", error=str(e), finished_at=utcnow())
            self.repo.set_internal(idea_id, analysis_status="failed", analysis_error=str(e))
            return
        result = {"brief": brief.model_dump(), "inputs": inputs.summary(), "provider": provider.name, "model": model,
                  "usage": usage, "generated_at": utcnow(), "edited": False}
        self._job_update("analysis_jobs", job_id, status="done", finished_at=utcnow())
        self.repo.set_internal(idea_id, analysis_status="done", analysis_error=None, analysis_json=_json(result))

    def save_edited_analysis(self, idea_id: str, brief: dict[str, Any]) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        validated = analysis_svc.CreativeBrief.model_validate(brief)
        current = idea.get("analysis") or {"inputs": {}, "provider": "manual", "model": ""}
        current.update({"brief": validated.model_dump(), "edited": True, "edited_at": utcnow()})
        self.repo.set_internal(idea_id, analysis_status="done", analysis_json=_json(current))
        return self.repo.idea(idea_id)  # type: ignore[return-value]

    def _attachments(self, idea_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.connection().execute("SELECT * FROM attachments WHERE idea_id=?", (idea_id,))]


def _json(obj: Any) -> str:
    import json
    return json.dumps(obj, default=str)
