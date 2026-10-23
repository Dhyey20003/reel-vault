"""The Workspace wires storage, settings and background work together (v2)."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from . import __version__
from .config import Paths, default_media_dir, get_ai_api_key
from .db import Database, new_id, utcnow
from .repo import Repo
from .services import analysis as analysis_svc
from .services import downloader, local_ai, media as media_svc, metadata as metadata_svc, resolve, tools
from .services.jobs import JobRunner

log = logging.getLogger("reelvault.workspace")
RESUMABLE_STAGES = ("queued_download", "downloading", "queued_analysis", "analyzing")


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str)


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
        t = tools.detect_tools(self.setting("ytdlp_path") or "", self.setting("ffmpeg_path") or "")
        w = local_ai.find_whisper(self.setting("whisper_path") or "")
        t["whisper"] = {"found": bool(w), "path": w,
                        "install_hint": "Optional local transcription: brew install whisper-cpp (macOS) or pip install openai-whisper; then set the path in Settings if it is not on PATH."}
        return t

    def ai_status(self) -> dict[str, Any]:
        provider = self.setting("ai_provider") or "ollama"
        out: dict[str, Any] = {"provider": provider}
        if provider == "ollama":
            st = local_ai.ollama_status(self.setting("ollama_url") or "http://127.0.0.1:11434", self.setting("ollama_model") or "")
            out.update(model=st["model"], configured=st["reachable"] and st["model_installed"], local=True, ollama=st,
                       how_to_configure="Install Ollama (https://ollama.com), run 'ollama pull " + (st["model"] or "qwen2.5vl:7b") + "', keep Ollama running. See docs/LOCAL_AI.md.")
            if st["error"]:
                out["how_to_configure"] = st["error"]
        else:
            key = get_ai_api_key(self.paths, provider)
            opt = bool(self.setting("cloud_ai_opt_in"))
            out.update(model=self.setting("ai_model"), configured=bool(key) and opt, local=False,
                       how_to_configure=("Cloud AI is opt-in: enable it in Settings. " if not opt else "") +
                       "Set REELVAULT_AI_API_KEY (or ANTHROPIC_API_KEY) or add {\"ai_api_key\": \"...\"} to " + str(self.paths.config_file))
        return out

    def status(self) -> dict[str, Any]:
        hw = local_ai.hardware()
        return {"version": self.version, "data_dir": str(self.paths.data_dir), "media_dir": str(self.media_dir()),
                "db_path": str(self.paths.db_path), "schema_version": self.db.current_version(),
                "tools": self.tools(), "ai": self.ai_status(), "hardware": hw,
                "resolve": resolve.detect(self.setting("resolve_scripting_path") or ""),
                "counts": self.repo.counts(), "pipeline": self.pipeline_status()}

    def _free_gb(self) -> float:
        d = self.media_dir()
        d.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(d).free / 1e9

    def _disk_ok(self) -> tuple[bool, str]:
        free = self._free_gb()
        need = float(self.setting("min_free_gb") or 0)
        return (free >= need, f"{free:.1f} GB free; minimum is {need:g} GB")

    # ---------------------------------------------------------------- metadata
    def queue_metadata(self, idea_id: str, force: bool = False) -> bool:
        idea = self.repo.idea(idea_id)
        if not idea or idea["source"] == "local":
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
            return
        fields: dict[str, Any] = {"metadata_status": "ok", "metadata_error": None, "metadata_provider": md.provider,
                                  "metadata_json": _json(md.raw)}
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
                if not fresh.get("cover_path"):
                    fields["thumbnail_path"] = str(dest)
            except Exception as e:  # noqa: BLE001
                log.info("thumbnail download failed for %s: %s", idea_id, e)
        self.repo.set_internal(idea_id, **fields)

    # ------------------------------------------------------------------ media
    def prepare_media(self, idea_id: str) -> dict[str, Any]:
        """Validates the local file, creates a browser-playable copy if needed, generates a cover if missing."""
        idea = self.repo.idea(idea_id)
        if not idea or not idea.get("local_path") or not Path(idea["local_path"]).is_file():
            self.repo.set_internal(idea_id, media_status="missing", playback_path=None)
            return {"status": "missing"}
        t = self.tools()
        src = Path(idea["local_path"])
        info = media_svc.probe(t["ffprobe"]["path"], src)
        fields: dict[str, Any] = {"media_status": info["status"], "media_json": _json(info)}
        if info["status"] == "ok":
            if media_svc.browser_compatible(info, src):
                fields["playback_path"] = str(src)
            elif t["ffmpeg"]["found"]:
                dest = self.paths.data_dir / "playback" / f"{idea_id}.mp4"
                if not (dest.is_file() and dest.stat().st_mtime >= src.stat().st_mtime):
                    ok, msg = self._disk_ok()
                    if not ok:
                        fields["playback_path"] = None; fields["pipeline_error"] = "not enough disk space for a playback copy: " + msg
                    else:
                        try:
                            media_svc.make_playback_copy(t["ffmpeg"]["path"], src, dest, info)
                            fields["playback_path"] = str(dest)
                        except Exception as e:  # noqa: BLE001
                            fields["playback_path"] = None; fields["pipeline_error"] = f"conversion failed: {e}"
                else:
                    fields["playback_path"] = str(dest)
            else:
                fields["playback_path"] = None
            if t["ffmpeg"]["found"] and not idea.get("cover_path") and not (idea.get("thumbnail_path") and Path(idea["thumbnail_path"]).is_file()):
                tsec = min(1.0, (info.get("duration") or 2) / 2)
                cov = media_svc.frame_at(t["ffmpeg"]["path"], src, self.paths.thumbnails / f"{idea_id}_gen.jpg", tsec)
                if cov:
                    fields["thumbnail_path"] = str(cov)
        else:
            fields["playback_path"] = None
        self.repo.set_internal(idea_id, **fields)
        return info

    def set_cover(self, idea_id: str, t: float | None = None, upload: Path | None = None) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        dest = self.paths.thumbnails / f"{idea_id}_cover.jpg"
        if upload is not None:
            dest = dest.with_suffix(upload.suffix.lower() or ".jpg")
            shutil.copy2(upload, dest)
            self.repo.set_internal(idea_id, cover_path=str(dest), cover_time=None)
        else:
            tl = self.tools()
            src = Path(idea.get("playback_path") or idea.get("local_path") or "")
            if not src.is_file() or not tl["ffmpeg"]["found"]:
                raise ValueError("A local video and ffmpeg are needed to pick a cover frame")
            out = media_svc.frame_at(tl["ffmpeg"]["path"], src, dest, float(t or 0))
            if not out:
                raise ValueError("Could not extract that frame")
            self.repo.set_internal(idea_id, cover_path=str(out), cover_time=float(t or 0))
        return self.repo.idea(idea_id)  # type: ignore[return-value]

    def import_local(self, file: Path, title: str = "") -> tuple[dict[str, Any], bool]:
        ok, msg = self._disk_ok()
        if not ok:
            raise ValueError("Not enough disk space: " + msg)
        digest = media_svc.content_hash(file)
        norm = f"local:{digest}"
        existing = self.repo.find_by_normalized(norm)
        if existing:
            return self.repo.idea(existing["id"]), False  # type: ignore[return-value]
        folder = self.media_dir() / "Imported"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / file.name
        i = 1
        while dest.exists():
            dest = folder / f"{file.stem} ({i}){file.suffix}"; i += 1
        shutil.move(str(file), dest)
        idea, created = self.repo.create_idea(f"local://{dest.name}", source="local", title=title or dest.stem,
                                              normalized_override=norm)
        self.repo.set_internal(idea["id"], download_status="downloaded", local_path=str(dest), metadata_status="ok",
                               metadata_provider="local")
        self.prepare_media(idea["id"])
        return self.repo.idea(idea["id"]), True  # type: ignore[return-value]

    # ---------------------------------------------------------------- download
    def queue_download(self, idea_id: str, *, from_pipeline: bool = False) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        if idea["source"] == "local":
            return {"ok": False, "error": "Imported files do not need downloading"}
        t = self.tools()
        if not t["ytdlp"]["found"]:
            return {"ok": False, "error": "yt-dlp is not installed. " + t["ytdlp"]["install_hint"]}
        ok, msg = self._disk_ok()
        if not ok:
            return {"ok": False, "error": "Not enough free disk space: " + msg}
        if idea["download_status"] in ("queued", "downloading") and self.jobs.is_running(f"download:{idea_id}"):
            return {"ok": True, "job_id": None, "note": "already in progress"}
        job_id = new_id()
        with self.db.tx() as conn:
            conn.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES (?,?,?,?)", (job_id, idea_id, "queued", utcnow()))
        self.repo.set_internal(idea_id, download_status="queued", download_error=None, pipeline_stage="queued_download", pipeline_error=None)
        self.jobs.submit(f"download:{idea_id}", lambda: self._run_download(job_id, idea_id, t))
        return {"ok": True, "job_id": job_id}

    def cancel_download(self, idea_id: str) -> bool:
        with self.db.tx() as conn:
            n = conn.execute("UPDATE download_jobs SET cancel_requested=1 WHERE idea_id=? AND status IN ('queued','downloading')", (idea_id,)).rowcount
        return n > 0

    def _download_target(self, idea: dict[str, Any]) -> Path:
        trip = idea["trips"][0]["name"] if idea.get("trips") else "General"
        return self.media_dir() / downloader.safe_folder_name(trip)

    def _run_download(self, job_id: str, idea_id: str, t: dict[str, Any]) -> None:
        idea = self.repo.idea(idea_id)
        if not idea:
            return
        self._job_update("download_jobs", job_id, status="downloading", started_at=utcnow())
        self.repo.set_internal(idea_id, download_status="downloading", pipeline_stage="downloading")
        last = {"p": 0.0}

        def progress(p: float, line: str) -> None:
            if p - last["p"] >= 2 or p >= 100:
                last["p"] = p
                self._job_update("download_jobs", job_id, progress=p)

        def cancelled() -> bool:
            row = self.db.connection().execute("SELECT cancel_requested FROM download_jobs WHERE id=?", (job_id,)).fetchone()
            return bool(row and row[0])
        try:
            out = downloader.run_download(ytdlp_path=t["ytdlp"]["path"], ffmpeg_path=t["ffmpeg"]["path"],
                                          url=idea["canonical_url"] or idea["original_url"], target_dir=self._download_target(idea),
                                          idea_id=idea_id, on_progress=progress, quality=self.setting("download_quality") or "best",
                                          should_cancel=cancelled)
        except downloader.DownloadError as e:
            self._job_update("download_jobs", job_id, status="failed", error=str(e), finished_at=utcnow())
            self.repo.set_internal(idea_id, download_status="failed", download_error=str(e), pipeline_stage="failed", pipeline_error=str(e))
            return
        info = media_svc.probe(t["ffprobe"]["path"], out)
        if info["status"] == "audio_only":
            msg = "yt-dlp produced an audio-only file (no video stream). The file is kept at " + str(out) + ". Install ffmpeg so video and audio can be merged, then download again."
            self._job_update("download_jobs", job_id, status="failed", error=msg, output_path=str(out), finished_at=utcnow())
            self.repo.set_internal(idea_id, download_status="failed", download_error=msg, local_path=str(out), media_status="audio_only",
                                   media_json=_json(info), pipeline_stage="failed", pipeline_error=msg)
            return
        if info["status"] == "invalid":
            msg = "Downloaded file is not a valid video: " + str(info.get("error"))
            self._job_update("download_jobs", job_id, status="failed", error=msg, output_path=str(out), finished_at=utcnow())
            self.repo.set_internal(idea_id, download_status="failed", download_error=msg, local_path=str(out), media_status="invalid",
                                   media_json=_json(info), pipeline_stage="failed", pipeline_error=msg)
            return
        self._job_update("download_jobs", job_id, status="downloaded", progress=100.0, output_path=str(out), finished_at=utcnow())
        self.repo.set_internal(idea_id, download_status="downloaded", download_error=None, local_path=str(out), pipeline_stage="downloaded")
        self.prepare_media(idea_id)
        self._pipeline_after_download(idea_id)

    def verify_download(self, idea_id: str) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        lp = idea.get("local_path")
        exists = bool(lp) and Path(lp).is_file() and Path(lp).stat().st_size > 0
        if idea["download_status"] == "downloaded" and not exists:
            self.repo.set_internal(idea_id, download_status="not_downloaded", local_path=None, playback_path=None, media_status="missing",
                                   download_error="The local file is missing; download again")
        elif exists:
            self.prepare_media(idea_id)
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
    def _provider(self) -> tuple[Any, str, str]:
        name = self.setting("ai_provider") or "ollama"
        settings = self.db.all_settings()
        key = get_ai_api_key(self.paths, name) if name != "ollama" else None
        provider = analysis_svc.build_provider(name, key, settings)
        model = (self.setting("ollama_model") if name == "ollama" else self.setting("ai_model")) or ""
        return provider, name, model

    def analysis_cache_key(self, idea: dict[str, Any], model: str, provider: str) -> str:
        parts = [provider, model, idea.get("title") or "", idea.get("caption") or "", idea.get("notes") or "", idea.get("transcript") or "",
                 str(self.setting("ai_max_frames")), str(bool(self.setting("ai_transcribe")))]
        lp = idea.get("local_path")
        if lp and Path(lp).is_file():
            parts.append(media_svc.file_fingerprint(Path(lp)))
        parts += [a["id"] for a in idea.get("attachments", []) if a.get("kind") == "screenshot"]
        return hashlib.sha1("|".join(parts).encode()).hexdigest()

    def queue_analysis(self, idea_id: str, *, force: bool = False, from_pipeline: bool = False) -> dict[str, Any]:
        idea = self.repo.idea(idea_id)
        if not idea:
            raise KeyError(idea_id)
        try:
            provider, name, model = self._provider()
        except analysis_svc.NotConfigured as e:
            return {"ok": False, "error": str(e), "configured": False}
        if from_pipeline and name != "ollama":
            return {"ok": False, "error": "Automatic analysis only runs with the local provider"}
        key = self.analysis_cache_key(idea, model, name)
        if not force and idea.get("analysis") and idea.get("analysis_cache_key") == key and idea.get("analysis_status") == "done":
            return {"ok": True, "cached": True, "note": "inputs, model and settings unchanged; existing brief kept"}
        if self.jobs.is_running(f"analysis:{idea_id}"):
            return {"ok": True, "note": "already running"}
        job_id = new_id()
        with self.db.tx() as conn:
            conn.execute("INSERT INTO analysis_jobs(id, idea_id, status, provider, model, created_at) VALUES (?,?,?,?,?,?)",
                         (job_id, idea_id, "queued", name, model, utcnow()))
        self.repo.set_internal(idea_id, analysis_status="queued", analysis_error=None, pipeline_stage="queued_analysis")
        self.jobs.submit(f"analysis:{idea_id}", lambda: self._run_analysis(job_id, idea_id, provider, name, model, key))
        return {"ok": True, "job_id": job_id}

    def cancel_analysis(self, idea_id: str) -> bool:
        with self.db.tx() as conn:
            n = conn.execute("UPDATE analysis_jobs SET cancel_requested=1 WHERE idea_id=? AND status IN ('queued','running')", (idea_id,)).rowcount
        return n > 0

    def _run_analysis(self, job_id: str, idea_id: str, provider: Any, name: str, model: str, cache_key: str) -> None:
        idea = self.repo.idea(idea_id)
        if not idea:
            return

        def cancelled() -> bool:
            row = self.db.connection().execute("SELECT cancel_requested FROM analysis_jobs WHERE id=?", (job_id,)).fetchone()
            return bool(row and row[0])

        def fail(msg: str) -> None:
            self._job_update("analysis_jobs", job_id, status="failed", error=msg, finished_at=utcnow())
            self.repo.set_internal(idea_id, analysis_status="failed", analysis_error=msg, pipeline_stage="failed", pipeline_error=msg)

        self._job_update("analysis_jobs", job_id, status="running", started_at=utcnow(), progress="preparing inputs")
        self.repo.set_internal(idea_id, analysis_status="running", pipeline_stage="analyzing")
        t = self.tools()
        frames: list[Path] = []
        times: list[float] = []
        transcript = idea.get("transcript") or ""
        tsource = "user" if transcript else ""
        src = Path(idea.get("playback_path") or idea.get("local_path") or "")
        n_frames = int(self.setting("ai_max_frames") or 0)
        if src.is_file() and t["ffmpeg"]["found"] and n_frames > 0 and (idea.get("media_status") in ("ok", "unknown", "unprobed")):
            info = media_svc.probe(t["ffprobe"]["path"], src)
            frame_dir = self.paths.tmp / "frames" / idea_id
            shutil.rmtree(frame_dir, ignore_errors=True)
            times = media_svc.scene_sample_times(t["ffmpeg"]["path"], src, info.get("duration") or 15.0, n_frames)
            self._job_update("analysis_jobs", job_id, progress=f"extracting {len(times)} frames")
            for i, ts in enumerate(times):
                if cancelled():
                    return fail("cancelled")
                f = media_svc.frame_at(t["ffmpeg"]["path"], src, frame_dir / f"frame_{i + 1:02d}.jpg", ts, width=640)
                if f:
                    frames.append(f)
            if not transcript and self.setting("ai_transcribe") and t["whisper"]["found"] and info.get("audio_codec"):
                self._job_update("analysis_jobs", job_id, progress="transcribing audio locally")
                txt = local_ai.transcribe(t["whisper"]["path"], t["ffmpeg"]["path"], src, self.paths.tmp / "whisper" / idea_id)
                if txt:
                    transcript, tsource = txt, "local-whisper"
        shots = [Path(a["path"]) for a in self._attachments(idea_id) if a["kind"] == "screenshot" and Path(a["path"]).is_file()]
        inputs = analysis_svc.AnalysisInputs(url=idea["canonical_url"] or idea["original_url"], title=idea["title"], creator=idea["creator"],
                                             caption=idea["caption"], notes=idea["notes"], transcript=transcript, frames=frames,
                                             screenshots=shots, frame_times=times[:len(frames)], transcript_source=tsource)
        self._job_update("analysis_jobs", job_id, inputs_json=_json(inputs.summary()), progress=f"asking {name} ({model})")
        if cancelled():
            return fail("cancelled")
        try:
            brief, usage = provider.analyze(inputs, model)
        except analysis_svc.AnalysisError as e:
            return fail(str(e))
        except Exception as e:  # noqa: BLE001
            return fail(f"{type(e).__name__}: {e}")
        if cancelled():
            return fail("cancelled")
        result = {"brief": brief.model_dump(), "inputs": inputs.summary(), "provider": name, "model": model, "usage": usage,
                  "generated_at": utcnow(), "edited": False}
        self._job_update("analysis_jobs", job_id, status="done", finished_at=utcnow(), progress="done")
        fields: dict[str, Any] = {"analysis_status": "done", "analysis_error": None, "analysis_json": _json(result),
                                  "analysis_cache_key": cache_key, "pipeline_stage": "done", "pipeline_error": None}
        if transcript and tsource == "local-whisper" and not idea.get("transcript"):
            fields["transcript"] = transcript
        self.repo.set_internal(idea_id, **fields)

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

    def test_local_ai(self) -> dict[str, Any]:
        """Round-trip a tiny prompt through the configured local model. No media is sent."""
        st = local_ai.ollama_status(self.setting("ollama_url") or "http://127.0.0.1:11434", self.setting("ollama_model") or "")
        if not (st["reachable"] and st["model_installed"]):
            return {"ok": False, "error": st["error"], "status": st}
        try:
            p = local_ai.OllamaProvider(st["url"], 120, 2048)
            raw = p._chat(st["model"], [{"role": "user", "content": 'Reply with JSON {"ok": true, "hello": "<one word greeting>"}'}],
                          {"type": "object", "properties": {"ok": {"type": "boolean"}, "hello": {"type": "string"}}, "required": ["ok"]})
            data = json.loads(raw)
            return {"ok": bool(data.get("ok")), "reply": data, "status": st}
        except (analysis_svc.AnalysisError, ValueError) as e:
            return {"ok": False, "error": str(e), "status": st}

    # ----------------------------------------------------------------- pipeline
    def pipeline_status(self) -> dict[str, Any]:
        conn = self.db.connection()
        rows = conn.execute("SELECT pipeline_stage, COUNT(*) AS n FROM ideas WHERE deleted_at IS NULL GROUP BY pipeline_stage").fetchall()
        return {"paused": bool(self.setting("pipeline_paused")), "auto_download": bool(self.setting("auto_download")),
                "auto_analyze": bool(self.setting("auto_analyze")), "stages": {r["pipeline_stage"]: r["n"] for r in rows},
                "free_gb": round(self._free_gb(), 1)}

    def on_capture_synced(self, idea_id: str) -> None:
        if self.setting("metadata_auto", True):
            self.queue_metadata(idea_id)
        if self.setting("auto_download") and not self.setting("pipeline_paused"):
            self.queue_download(idea_id, from_pipeline=True)

    def _pipeline_after_download(self, idea_id: str) -> None:
        if self.setting("auto_analyze") and not self.setting("pipeline_paused"):
            self.queue_analysis(idea_id, from_pipeline=True)

    def resume_pipeline(self) -> dict[str, int]:
        """Called at startup: re-queue stages interrupted by a restart."""
        resumed = {"download": 0, "analysis": 0, "metadata": 0}
        if self.setting("pipeline_paused"):
            return resumed
        conn = self.db.connection()
        for row in conn.execute("SELECT id, pipeline_stage, download_status, analysis_status FROM ideas WHERE deleted_at IS NULL"):
            stage = row["pipeline_stage"]
            if stage in ("queued_download", "downloading") or row["download_status"] in ("queued", "downloading"):
                self.repo.set_internal(row["id"], download_status="not_downloaded")
                if self.queue_download(row["id"], from_pipeline=True).get("ok"):
                    resumed["download"] += 1
            elif stage in ("queued_analysis", "analyzing") or row["analysis_status"] in ("queued", "running"):
                self.repo.set_internal(row["id"], analysis_status="none")
                if self.queue_analysis(row["id"], from_pipeline=True).get("ok"):
                    resumed["analysis"] += 1
        with self.db.tx() as c:
            c.execute("UPDATE download_jobs SET status='failed', error='interrupted by restart' WHERE status IN ('queued','downloading')")
            c.execute("UPDATE analysis_jobs SET status='failed', error='interrupted by restart' WHERE status IN ('queued','running')")
        if self.setting("metadata_auto", True):
            for row in conn.execute("SELECT id FROM ideas WHERE deleted_at IS NULL AND metadata_status IN ('pending','fetching') LIMIT 50"):
                if self.queue_metadata(row["id"], force=True):
                    resumed["metadata"] += 1
        return resumed

    # ------------------------------------------------------------------ repair
    def repair_scan(self) -> dict[str, Any]:
        t = self.tools()
        ai = self.ai_status()
        conn = self.db.connection()
        issues: list[dict[str, Any]] = []
        if not t["ytdlp"]["found"]:
            issues.append({"kind": "tool", "id": "ytdlp", "title": "yt-dlp not installed", "detail": t["ytdlp"]["install_hint"], "action": None})
        if not t["ffmpeg"]["found"]:
            issues.append({"kind": "tool", "id": "ffmpeg", "title": "ffmpeg not installed (needed for video+audio merging, playback copies, covers)", "detail": t["ffmpeg"]["install_hint"], "action": None})
        if not ai.get("configured"):
            issues.append({"kind": "ai", "id": "ai", "title": "Local AI not ready", "detail": ai.get("how_to_configure"), "action": "test_ai"})
        for r in conn.execute("SELECT id, title, original_url, download_status, download_error, local_path, media_status, thumbnail_path, cover_path, metadata_status, metadata_error FROM ideas WHERE deleted_at IS NULL"):
            label = r["title"] or r["original_url"]
            lp = r["local_path"]
            if r["media_status"] == "audio_only" or (r["download_status"] == "failed" and "audio-only" in (r["download_error"] or "")):
                issues.append({"kind": "audio_only", "id": r["id"], "title": f"Audio-only download: {label}", "detail": "Re-download with ffmpeg installed to get video + audio. The existing file is kept.", "action": "redownload"})
            elif r["download_status"] == "failed":
                issues.append({"kind": "download_failed", "id": r["id"], "title": f"Download failed: {label}", "detail": r["download_error"], "action": "redownload"})
            elif r["download_status"] == "downloaded" and (not lp or not Path(lp).is_file()):
                issues.append({"kind": "missing_file", "id": r["id"], "title": f"Missing file: {label}", "detail": lp, "action": "verify"})
            elif r["download_status"] == "downloaded" and r["media_status"] in ("unknown", "unprobed", "invalid"):
                issues.append({"kind": "unvalidated", "id": r["id"], "title": f"Media not validated: {label}", "detail": r["media_status"], "action": "prepare"})
            has_thumb = (r["cover_path"] and Path(r["cover_path"]).is_file()) or (r["thumbnail_path"] and Path(r["thumbnail_path"]).is_file())
            if not has_thumb and lp and Path(lp).is_file() and t["ffmpeg"]["found"]:
                issues.append({"kind": "missing_thumb", "id": r["id"], "title": f"No thumbnail: {label}", "detail": "generate a cover from the video", "action": "prepare"})
            if r["metadata_status"] == "unavailable":
                issues.append({"kind": "metadata", "id": r["id"], "title": f"Metadata unavailable: {label}", "detail": r["metadata_error"], "action": "metadata"})
        devices = self.repo.devices()
        return {"issues": issues, "tools": t, "ai": ai, "devices": devices, "lan": self.lan_info()}

    def diagnostics(self) -> dict[str, Any]:
        """Redacted diagnostics for support: no token, no key, no file contents."""
        s = self.db.all_settings()
        for k in ("instagram_oembed_token",):
            s[k] = "<set>" if s.get(k) else ""
        st = self.status()
        logp = self.paths.logs / "reelvault.log"
        tail = ""
        if logp.is_file():
            tail = logp.read_text(encoding="utf-8", errors="replace")[-20000:]
            import re
            tail = re.sub(r"(token|key)=\S+", r"\1=<redacted>", tail, flags=re.I)
        return {"status": st, "settings": s, "repair": self.repair_scan()["issues"], "log_tail": tail}

    def lan_info(self) -> dict[str, Any]:
        from .netutil import lan_candidates
        cands = lan_candidates()
        chosen = self.setting("advertised_host") or (cands[0]["ip"] if cands else None)
        return {"candidates": cands, "advertised_host": chosen, "configured": bool(self.setting("advertised_host"))}

    # --------------------------------------------------------------- trip plans
    def adapt_for_trip(self, trip_id: str, idea_ids: list[str], destination: str, gear: str, time_available: str, preferences: str) -> dict[str, Any]:
        trip = self.repo.trip(trip_id)
        if not trip:
            raise KeyError(trip_id)
        try:
            provider, name, model = self._provider()
        except analysis_svc.NotConfigured as e:
            return {"ok": False, "error": str(e)}
        refs = []
        for iid in idea_ids:
            i = self.repo.idea(iid)
            if not i:
                continue
            a = (i.get("analysis") or {}).get("brief") or {}
            refs.append({"title": i.get("title") or i["original_url"], "notes": i.get("notes"), "tags": i.get("tags"),
                         "observed_facts": a.get("observed_facts"), "shot_list": a.get("shot_list"), "hook": a.get("opening_hook")})
        plan_id = new_id()
        inputs = {"destination": destination or trip.get("location") or trip["name"], "gear": gear, "time": time_available,
                  "preferences": preferences, "references": refs}
        with self.db.tx() as conn:
            conn.execute("INSERT INTO trip_plans(id, trip_id, inputs_json, status, provider, model, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                         (plan_id, trip_id, _json(inputs), "queued", name, model, utcnow(), utcnow()))
        self.jobs.submit(f"plan:{plan_id}", lambda: self._run_plan(plan_id, provider, name, model, trip, inputs))
        return {"ok": True, "plan_id": plan_id}

    def _run_plan(self, plan_id: str, provider: Any, name: str, model: str, trip: dict[str, Any], inputs: dict[str, Any]) -> None:
        from .services.analysis import TripPlan
        self._job_update("trip_plans", plan_id, status="running", updated_at=utcnow())
        prompt = ("Create a practical shot list and recreation plan for a short-form video trip.\n"
                  f"Trip: {trip['name']}. Destination: {inputs['destination']}. Available gear: {inputs['gear'] or 'unknown'}. "
                  f"Time available: {inputs['time'] or 'unknown'}. Preferences: {inputs['preferences'] or 'none'}.\n"
                  "Reference inspirations (observed details come from earlier analyses; treat them as facts about the references, "
                  "everything you add is a proposal):\n" + json.dumps(inputs["references"], ensure_ascii=False)[:12000] +
                  "\nReturn JSON with fields: observed_from_references (list), proposed_shots (list of {shot, description, location_hint, duration_seconds, gear}), "
                  "schedule (list of strings), recreation_plan (string), gear_checklist (list), risks (list), notes (string).")
        try:
            if hasattr(provider, "plan"):
                data = provider.plan(model, prompt, TripPlan.model_json_schema())
            else:
                raise analysis_svc.AnalysisError("This provider cannot generate trip plans")
            plan = TripPlan.model_validate(data)
        except Exception as e:  # noqa: BLE001
            self._job_update("trip_plans", plan_id, status="failed", error=str(e)[:400], updated_at=utcnow())
            return
        self._job_update("trip_plans", plan_id, status="done", plan_json=_json(plan.model_dump()), updated_at=utcnow())

    def trip_plans(self, trip_id: str) -> list[dict[str, Any]]:
        rows = [dict(r) for r in self.db.connection().execute("SELECT * FROM trip_plans WHERE trip_id=? ORDER BY created_at DESC LIMIT 10", (trip_id,))]
        for r in rows:
            r["inputs"] = json.loads(r.pop("inputs_json") or "{}")
            r["plan"] = json.loads(r.pop("plan_json")) if r.get("plan_json") else None
        return rows

    def save_plan(self, plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from .services.analysis import TripPlan
        validated = TripPlan.model_validate(plan)
        self._job_update("trip_plans", plan_id, plan_json=_json(validated.model_dump()), status="done", updated_at=utcnow())
        return validated.model_dump()
