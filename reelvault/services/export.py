"""Exports: shot lists (Markdown / plain text) and whole-trip export folders.

Originals are only ever copied, never moved, renamed or deleted.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import brief_to_markdown
from .downloader import safe_folder_name


def _md_to_text(md: str) -> str:
    out = []
    for line in md.splitlines():
        line = re.sub(r"^#+\s*", "", line)
        line = line.replace("**", "")
        out.append(line)
    return "\n".join(out)


def shot_list_document(ideas: list[dict[str, Any]], fmt: str = "md", heading: str = "Shot list") -> str:
    parts = [f"# {heading}", f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_", ""]
    for idea in ideas:
        title = idea.get("title") or idea.get("original_url")
        parts.append(f"## {title}")
        parts.append(f"Link: {idea.get('original_url')}")
        if idea.get("creator"):
            parts.append(f"Creator: {idea['creator']}")
        parts.append(f"Priority: {idea.get('priority')}  |  Status: {idea.get('status')}")
        if idea.get("notes"):
            parts += ["", "Notes:", idea["notes"]]
        if idea.get("shooting_notes"):
            parts += ["", "Shooting notes:", idea["shooting_notes"]]
        if idea.get("editing_notes"):
            parts += ["", "Editing notes:", idea["editing_notes"]]
        if idea.get("local_path"):
            parts.append(f"Local reference: {idea['local_path']}")
        analysis = idea.get("analysis")
        if analysis:
            parts += ["", brief_to_markdown(analysis).replace("# Creative brief", "### Creative brief", 1)]
        else:
            parts.append("(no AI analysis saved for this idea)")
        parts.append("")
    md = "\n".join(parts)
    return md if fmt == "md" else _md_to_text(md)


def export_trip(trip: dict[str, Any], ideas: list[dict[str, Any]], exports_dir: Path, copy_media: bool = True) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = exports_dir / f"{safe_folder_name(trip['name'])}-{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "trip.json").write_text(json.dumps({"trip": trip, "ideas": ideas}, indent=2, default=str), encoding="utf-8")
    lines = [f"# {trip['name']}", ""]
    for key, label in (("location", "Location"), ("description", "Description"), ("start_date", "Start"), ("end_date", "End")):
        if trip.get(key):
            lines.append(f"- {label}: {trip[key]}")
    if trip.get("notes"):
        lines += ["", "## Notes", trip["notes"]]
    if trip.get("checklist"):
        lines += ["", "## Checklist"] + [f"- [{'x' if c.get('done') else ' '}] {c.get('text', '')}" for c in trip["checklist"]]
    high = [i for i in ideas if i.get("priority") == "High"]
    if high:
        lines += ["", "## High priority"] + [f"- {i.get('title') or i['original_url']}" for i in high]
    lines += ["", "## References"]
    refs = folder / "references"
    copied = 0
    for idea in ideas:
        lines.append(f"- {idea.get('title') or idea['original_url']} ({idea.get('status')}) {idea['original_url']}")
        lp = idea.get("local_path")
        if copy_media and lp and Path(lp).is_file():
            refs.mkdir(exist_ok=True)
            dest = refs / Path(lp).name
            if not dest.exists():
                shutil.copy2(lp, dest)
                copied += 1
    lines += ["", f"_{copied} reference file(s) copied into references/_", ""]
    (folder / "trip.md").write_text("\n".join(lines), encoding="utf-8")
    (folder / "shotlist.md").write_text(shot_list_document(ideas, "md", f"Shot list: {trip['name']}"), encoding="utf-8")
    return folder
