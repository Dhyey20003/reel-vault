"""DaVinci Resolve integration: detection only, never assumed.

ReelVault organizes references on disk by trip so Resolve's media pool can import a folder.
If the Resolve scripting API is installed (and Resolve is running), the optional
``import_to_media_pool`` call creates a bin named after the trip and imports the reference
files. It never moves, renames, deletes or overwrites any footage.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def candidate_module_dirs(configured: str = "") -> list[Path]:
    dirs: list[Path] = []
    if configured:
        dirs.append(Path(configured))
    env = os.environ.get("RESOLVE_SCRIPT_API")
    if env:
        dirs.append(Path(env) / "Modules")
    if os.name == "nt":
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        dirs.append(Path(pd) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting" / "Modules")
    elif sys.platform == "darwin":
        dirs.append(Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"))
    else:
        dirs.append(Path("/opt/resolve/Developer/Scripting/Modules"))
    return dirs


def detect(configured: str = "") -> dict[str, Any]:
    for d in candidate_module_dirs(configured):
        if (d / "DaVinciResolveScript.py").is_file():
            return {"detected": True, "modules_dir": str(d), "note": "Scripting module found. Resolve must be running with external scripting enabled (Preferences > System > General) for imports."}
    return {"detected": False, "modules_dir": None,
            "note": "DaVinci Resolve scripting module not found. The folder-based workflow (organized references + exported notes) works without it."}


def import_to_media_pool(files: list[str], bin_name: str, configured: str = "") -> dict[str, Any]:
    info = detect(configured)
    if not info["detected"]:
        return {"ok": False, "error": info["note"]}
    mod_dir = info["modules_dir"]
    if mod_dir not in sys.path:
        sys.path.append(mod_dir)
    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-not-found]
        resolve = dvr.scriptapp("Resolve")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Could not connect to Resolve: {e}"}
    if not resolve:
        return {"ok": False, "error": "Resolve is not running or external scripting is disabled"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"ok": False, "error": "Open a project in Resolve first"}
    pool = project.GetMediaPool()
    root = pool.GetRootFolder()
    target = next((f for f in root.GetSubFolderList() if f.GetName() == bin_name), None) or pool.AddSubFolder(root, bin_name)
    pool.SetCurrentFolder(target)
    existing = [p for p in files if Path(p).is_file()]
    items = pool.ImportMedia(existing) if existing else []
    return {"ok": True, "imported": len(items or []), "bin": bin_name}
