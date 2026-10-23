"""Local AI: Ollama vision provider, hardware check, optional local transcription.

Nothing here talks to any host except the configured Ollama endpoint (localhost by default).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..netutil import is_private_client
from .analysis import AnalysisError, AnalysisInputs, CreativeBrief, NotConfigured, SYSTEM_PROMPT, parse_brief

log = logging.getLogger("reelvault.localai")
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Ollama vision-capable models (name, approx download GB, minimum RAM GB)
MODEL_CHOICES = [
    {"name": "qwen2.5vl:7b", "download_gb": 6.0, "min_ram_gb": 16, "note": "best quality for frames + text on 16 GB or more"},
    {"name": "gemma3:4b", "download_gb": 3.3, "min_ram_gb": 8, "note": "lighter, good general vision"},
    {"name": "llava:7b", "download_gb": 4.7, "min_ram_gb": 12, "note": "classic vision model"},
    {"name": "qwen2.5vl:3b", "download_gb": 3.2, "min_ram_gb": 8, "note": "smallest Qwen vision"},
]


def hardware() -> dict[str, Any]:
    mem = None
    try:
        if sys.platform == "darwin":
            mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout.strip())
        elif os.name == "nt":
            import ctypes
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); mem = int(m.ullTotalPhys)
        else:
            mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:  # noqa: BLE001
        mem = None
    chip = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        try:
            chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5).stdout.strip() or chip
        except Exception:  # noqa: BLE001
            pass
    disk = shutil.disk_usage(Path.home())
    return {"os": f"{platform.system()} {platform.release()}", "machine": platform.machine(), "chip": chip,
            "ram_gb": round(mem / 1e9, 1) if mem else None, "disk_free_gb": round(disk.free / 1e9, 1)}


def recommend_model(ram_gb: float | None) -> dict[str, Any]:
    if ram_gb is None:
        return MODEL_CHOICES[1]
    for m in MODEL_CHOICES:
        if ram_gb >= m["min_ram_gb"]:
            return m
    return MODEL_CHOICES[-1]


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise NotConfigured("Ollama URL must be http(s)://host:port")
    host = parts.hostname
    if host not in ("localhost",) and not host.endswith(".local") and not is_private_client(host):
        raise NotConfigured("Ollama endpoint must be on localhost or a private network; refusing " + host)


def ollama_status(url: str, model: str, timeout: float = 5.0) -> dict[str, Any]:
    out: dict[str, Any] = {"url": url, "model": model, "reachable": False, "model_installed": False, "models": [], "error": None}
    try:
        _check_url(url)
        req = urllib.request.Request(url.rstrip("/") + "/api/tags", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            data = json.loads(r.read().decode("utf-8", "replace"))
        names = [m.get("name", "") for m in data.get("models", [])]
        out.update(reachable=True, models=names, model_installed=any(n == model or n.split(":")[0] == model.split(":")[0] and (":" not in model or n == model) for n in names))
        if not out["model_installed"]:
            out["error"] = f"Model '{model}' is not installed. Run:  ollama pull {model}"
    except NotConfigured as e:
        out["error"] = str(e)
    except urllib.error.URLError as e:
        out["error"] = f"Ollama is not reachable at {url} ({e.reason}). Start it with:  ollama serve  (or open the Ollama app)"
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Ollama check failed: {e}"
    return out


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str, timeout: int = 600, num_ctx: int = 8192):
        _check_url(url)
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx

    def _chat(self, model: str, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> str:
        body = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.4, "num_ctx": self.num_ctx},
                "format": schema or "json"}
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
                data = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404 and "not found" in msg.lower():
                raise AnalysisError(f"Model '{model}' is not installed in Ollama. Run: ollama pull {model}") from e
            raise AnalysisError(f"Ollama error {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            raise AnalysisError(f"Ollama is not reachable at {self.url}: {e.reason}") from e
        except TimeoutError as e:
            raise AnalysisError(f"Ollama timed out after {self.timeout}s; try a smaller model or fewer frames") from e
        except OSError as e:
            raise AnalysisError(f"Ollama request failed: {e}") from e
        return (data.get("message") or {}).get("content") or ""

    def analyze(self, inputs: AnalysisInputs, model: str) -> tuple[CreativeBrief, dict[str, Any]]:
        import base64
        text = [f"URL: {inputs.url}"]
        if inputs.title: text.append(f"Title: {inputs.title}")
        if inputs.creator: text.append(f"Creator: {inputs.creator}")
        if inputs.caption: text.append(f"Caption/metadata:\n{inputs.caption}")
        if inputs.notes: text.append(f"My notes:\n{inputs.notes}")
        if inputs.transcript: text.append(f"Transcript (local speech-to-text, may contain errors):\n{inputs.transcript}")
        imgs = [p for p in inputs.frames + inputs.screenshots if p.is_file()][:12]
        if inputs.frames:
            text.append(f"{len(inputs.frames)} sampled still frames are attached in time order (timestamps: " +
                        ", ".join(f"{t:.1f}s" for t in inputs.frame_times[:len(inputs.frames)]) + "). You did NOT see the full video or hear audio.")
        if inputs.screenshots:
            text.append(f"{len(inputs.screenshots)} user screenshot(s) attached after the frames.")
        if not imgs:
            text.append("No images attached; the video itself was NOT provided.")
        text.append("Rules: observed_facts only from what is visible in frames or stated in the text. Put uncertain readings in confidence_note. "
                    "Do not guess exact camera models, lens, settings or sound details without evidence. Return JSON for the brief schema.")
        msg = {"role": "user", "content": "\n".join(text)}
        if imgs:
            msg["images"] = [base64.b64encode(p.read_bytes()).decode("ascii") for p in imgs]
        schema = CreativeBrief.model_json_schema()
        raw = self._chat(model, [{"role": "system", "content": SYSTEM_PROMPT}, msg], schema)
        try:
            brief = parse_brief(raw)
        except AnalysisError:
            # one repair attempt: ask the model to fix its own JSON
            raw2 = self._chat(model, [{"role": "system", "content": "Return only valid JSON matching the schema."},
                                      {"role": "user", "content": f"Fix this into valid JSON for schema {json.dumps(schema)[:3000]}:\n{raw[:6000]}"}], schema)
            brief = parse_brief(raw2)
        return brief, {"model": model, "endpoint": self.url, "images": len(imgs)}

    def plan(self, model: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        raw = self._chat(model, [{"role": "system", "content": "You are a practical video producer. Return JSON only."},
                                 {"role": "user", "content": prompt}], schema)
        try:
            return json.loads(raw)
        except ValueError as e:
            raise AnalysisError("Local model returned invalid JSON for the plan") from e


def find_whisper(configured: str = "") -> str | None:
    if configured and Path(configured).is_file():
        return configured
    for name in ("whisper-cli", "whisper-cpp", "whisper"):
        p = shutil.which(name)
        if p:
            return p
    return None


def transcribe(whisper: str, ffmpeg: str, video: Path, work: Path, timeout: int = 900) -> str | None:
    """Local transcription with whisper.cpp (whisper-cli) or the openai-whisper CLI. Returns text or None."""
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "audio16k.wav"
    try:
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-t", "600", str(wav)],
                       capture_output=True, timeout=300, creationflags=_FLAGS)
        if not wav.is_file() or wav.stat().st_size < 1000:
            return None
        name = Path(whisper).name
        if name.startswith("whisper-c"):
            out = subprocess.run([whisper, "-f", str(wav), "-nt", "-np"], capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS)
            txt = out.stdout
        else:
            subprocess.run([whisper, str(wav), "--output_dir", str(work), "--output_format", "txt", "--model", "base", "--fp16", "False"],
                           capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS)
            f = work / "audio16k.txt"
            txt = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
        txt = " ".join(txt.split())
        return txt[:8000] or None
    except (OSError, subprocess.SubprocessError):
        return None
