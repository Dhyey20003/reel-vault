"""Optional, on-demand AI analysis behind a provider abstraction.

* Never runs automatically; the user clicks "Analyze Reel".
* The API key is read from an environment variable or the data folder's config.json
  (see config.get_ai_api_key). It is never stored in the database, the exe or logs.
* The brief is validated against ``CreativeBrief`` before it is saved.
* ``observed_inputs`` records exactly which inputs the model was given so the UI can
  separate observed facts from suggestions and never claim a video was watched when only
  a URL/caption was available.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("reelvault.analysis")


class Shot(BaseModel):
    shot: str = Field(description="Short name, e.g. 'Wide establishing'")
    description: str = ""
    duration_seconds: float | None = None
    camera: str = ""


class CreativeBrief(BaseModel):
    observed_facts: list[str] = Field(default_factory=list, description="Only things directly supported by the provided inputs")
    core_idea: str = ""
    opening_hook: str = ""
    story_structure: str = ""
    shot_list: list[Shot] = Field(default_factory=list)
    camera_approach: str = ""
    editing_approach: str = ""
    sound_design: str = ""
    production_requirements: list[str] = Field(default_factory=list)
    recreation_plan: str = ""
    personal_notes: str = ""
    uncertain_interpretations: list[str] = Field(default_factory=list, description="Readings that are plausible but not certain from the inputs")
    confidence_note: str = Field(default="", description="What was and was not available to the model")


@dataclass
class AnalysisInputs:
    url: str
    title: str = ""
    creator: str = ""
    caption: str = ""
    notes: str = ""
    transcript: str = ""
    frames: list[Path] = field(default_factory=list)
    screenshots: list[Path] = field(default_factory=list)
    frame_times: list[float] = field(default_factory=list)
    transcript_source: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "url": True, "title": bool(self.title), "creator": bool(self.creator), "caption": bool(self.caption),
            "notes": bool(self.notes), "transcript": bool(self.transcript),
            "frames": len(self.frames), "screenshots": len(self.screenshots),
            "frame_times": [round(t, 1) for t in self.frame_times], "transcript_source": self.transcript_source,
            "video_watched": False, "audio_heard": False,
        }


class AnalysisProvider(Protocol):
    name: str
    def analyze(self, inputs: AnalysisInputs, model: str) -> tuple[CreativeBrief, dict[str, Any]]: ...


class AnalysisError(Exception):
    pass


class NotConfigured(AnalysisError):
    pass


SYSTEM_PROMPT = """You are a creative director helping a solo video creator recreate the spirit of a short-form
video (an Instagram Reel) in their own style. You are given whatever is available: the link, a title, creator name,
caption, the creator's own notes, maybe a transcript, maybe a few still frames or screenshots.

Rules:
- You cannot watch video. Only list facts that are directly visible in the provided text or images under
  observed_facts. Everything else is a suggestion.
- If only a URL and little else is provided, say so in confidence_note and keep suggestions generic but useful.
- Be concrete and practical: shot lists with durations, camera moves, edit rhythm, sound choices.
- Write for a travel/lifestyle creator who shoots on a phone or mirrorless camera.
- Keep each field concise. Shot list: 4 to 10 shots."""


def _user_content(inputs: AnalysisInputs) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    text = ["Reference reel inputs:", f"URL: {inputs.url}"]
    if inputs.title:
        text.append(f"Title: {inputs.title}")
    if inputs.creator:
        text.append(f"Creator: {inputs.creator}")
    if inputs.caption:
        text.append(f"Caption/metadata:\n{inputs.caption}")
    if inputs.notes:
        text.append(f"My notes:\n{inputs.notes}")
    if inputs.transcript:
        text.append(f"Transcript:\n{inputs.transcript}")
    imgs = [("extracted frame", p) for p in inputs.frames] + [("my screenshot", p) for p in inputs.screenshots]
    if imgs:
        text.append(f"{len(imgs)} image(s) attached, in order: " + ", ".join(f"{i + 1}={k}" for i, (k, _) in enumerate(imgs)))
    else:
        text.append("No images attached; the video itself was NOT provided.")
    parts.append({"type": "text", "text": "\n".join(text)})
    for _, p in imgs[:12]:
        data = p.read_bytes()
        if len(data) > 4_500_000:
            continue
        media = "image/png" if p.suffix.lower() == ".png" else "image/webp" if p.suffix.lower() == ".webp" else "image/jpeg"
        parts.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                  "data": base64.standard_b64encode(data).decode("ascii")}})
    parts.append({"type": "text", "text": "Produce the creative brief."})
    return parts


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def analyze(self, inputs: AnalysisInputs, model: str) -> tuple[CreativeBrief, dict[str, Any]]:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - dependency is pinned
            raise AnalysisError("The anthropic package is not installed") from e
        client = anthropic.Anthropic(api_key=self.api_key, max_retries=2, timeout=300.0)
        try:
            with client.messages.stream(
                model=model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _user_content(inputs)}],
                output_config={"format": {"type": "json_schema", "schema": CreativeBrief.model_json_schema()}},
            ) as stream:
                response = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise AnalysisError("The AI API key was rejected (authentication error)") from e
        except anthropic.RateLimitError as e:
            raise AnalysisError("The AI provider rate-limited the request; try again in a minute") from e
        except anthropic.APIStatusError as e:
            raise AnalysisError(f"AI provider error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AnalysisError("Could not reach the AI provider (network error)") from e
        if response.stop_reason == "refusal":
            raise AnalysisError("The AI provider declined this request")
        if response.stop_reason == "max_tokens":
            raise AnalysisError("The AI response was cut off; try again")
        text = "".join(b.text for b in response.content if b.type == "text")
        brief = parse_brief(text)
        usage = {"model": response.model, "input_tokens": response.usage.input_tokens,
                 "output_tokens": response.usage.output_tokens}
        return brief, usage


def parse_brief(text: str) -> CreativeBrief:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return CreativeBrief.model_validate(json.loads(text))
    except (ValueError, ValidationError) as e:
        raise AnalysisError(f"The AI reply did not match the brief schema: {str(e)[:200]}") from e


def build_provider(name: str, api_key: str | None, settings: dict[str, Any] | None = None) -> AnalysisProvider:
    settings = settings or {}
    if name == "ollama":
        from .local_ai import OllamaProvider
        return OllamaProvider(settings.get("ollama_url") or "http://127.0.0.1:11434", int(settings.get("ollama_timeout") or 600),
                              int(settings.get("ollama_num_ctx") or 8192))
    if name != "anthropic":
        raise NotConfigured(f"Unknown AI provider '{name}'. Supported: ollama (local), anthropic (cloud, opt-in)")
    if not settings.get("cloud_ai_opt_in"):
        raise NotConfigured("The Anthropic cloud provider is off. Local AI (Ollama) is the default; it is opt-in: enable 'cloud_ai_opt_in' in Settings to use the cloud provider.")
    if not api_key:
        raise NotConfigured(
            "No AI API key configured. Set the REELVAULT_AI_API_KEY (or ANTHROPIC_API_KEY) environment variable, "
            "or add {\"ai_api_key\": \"...\"} to config.json in the data folder, then restart ReelVault.")
    return AnthropicProvider(api_key)


def brief_to_markdown(brief: dict[str, Any], title: str = "") -> str:
    b = CreativeBrief.model_validate(brief) if not isinstance(brief, CreativeBrief) else brief
    lines = [f"# Creative brief{(': ' + title) if title else ''}", ""]
    if b.observed_facts:
        lines += ["## Observed facts (from provided inputs)"] + [f"- {f}" for f in b.observed_facts] + [""]
    for label, val in (("Core idea", b.core_idea), ("Opening hook", b.opening_hook), ("Story structure", b.story_structure)):
        if val:
            lines += [f"## {label}", val, ""]
    if b.shot_list:
        lines.append("## Shot list")
        for i, s in enumerate(b.shot_list, 1):
            dur = f" ({s.duration_seconds:g}s)" if s.duration_seconds else ""
            cam = f" [{s.camera}]" if s.camera else ""
            lines.append(f"{i}. **{s.shot}**{dur}{cam} {s.description}".rstrip())
        lines.append("")
    for label, val in (("Camera approach", b.camera_approach), ("Editing approach", b.editing_approach),
                       ("Sound design", b.sound_design)):
        if val:
            lines += [f"## {label}", val, ""]
    if b.uncertain_interpretations:
        lines += ["## Uncertain interpretations"] + [f"- {u}" for u in b.uncertain_interpretations] + [""]
    if b.production_requirements:
        lines += ["## Production requirements"] + [f"- {r}" for r in b.production_requirements] + [""]
    for label, val in (("Recreation plan", b.recreation_plan), ("Personal notes", b.personal_notes),
                       ("Confidence note", b.confidence_note)):
        if val:
            lines += [f"## {label}", val, ""]
    return "\n".join(lines).rstrip() + "\n"


class PlannedShot(BaseModel):
    shot: str
    description: str = ""
    location_hint: str = ""
    duration_seconds: float | None = None
    gear: str = ""


class TripPlan(BaseModel):
    """'Adapt for my trip' output. observed_from_references is copied from analyses; everything else is a proposal."""
    observed_from_references: list[str] = Field(default_factory=list)
    proposed_shots: list[PlannedShot] = Field(default_factory=list)
    schedule: list[str] = Field(default_factory=list)
    recreation_plan: str = ""
    gear_checklist: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    notes: str = ""
