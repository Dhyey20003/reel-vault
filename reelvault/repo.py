"""Data access for ideas, trips, categories and sync receipts.

Rows are returned as plain dicts so the API layer can serialize them directly.
Conflict handling is last-writer-wins on ``updated_at`` (documented in docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import STATUSES
from .db import Database, new_id, utcnow
from .urlnorm import extract_url, is_safe_url, normalize_url

IDEA_EDITABLE = {
    "title", "creator", "caption", "notes", "shooting_notes", "editing_notes", "transcript",
    "category_id", "priority", "status", "finished_video_url", "follow_up_date", "canonical_url",
    "thumbnail_url", "tags_json", "loop_start", "loop_end",
}
TAG_SUGGESTIONS = ["hook", "lighting", "camera movement", "transition", "colour", "sound", "storytelling", "pacing", "drone", "timelapse", "talking head", "b-roll"]


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


def _rows(rs: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rs]


class Repo:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ categories
    def categories(self) -> list[dict[str, Any]]:
        return _rows(self.db.connection().execute(
            "SELECT c.*, (SELECT COUNT(*) FROM ideas i WHERE i.category_id=c.id AND i.deleted_at IS NULL) AS idea_count "
            "FROM categories c ORDER BY sort_order, name"))

    def category_by_name(self, name: str) -> dict[str, Any] | None:
        return _row(self.db.connection().execute(
            "SELECT * FROM categories WHERE name=? COLLATE NOCASE", (name.strip(),)).fetchone())

    def create_category(self, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        existing = self.category_by_name(name)
        if existing:
            return existing
        now = utcnow()
        cid = new_id()
        with self.db.tx() as conn:
            order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories").fetchone()[0]
            conn.execute("INSERT INTO categories(id, name, sort_order, created_at, updated_at) VALUES (?,?,?,?,?)",
                         (cid, name, order, now, now))
        return self.category(cid)  # type: ignore[return-value]

    def category(self, cid: str) -> dict[str, Any] | None:
        return _row(self.db.connection().execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone())

    def rename_category(self, cid: str, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        other = self.category_by_name(name)
        if other and other["id"] != cid:
            raise ValueError("A category with that name already exists")
        with self.db.tx() as conn:
            conn.execute("UPDATE categories SET name=?, updated_at=? WHERE id=?", (name, utcnow(), cid))
        cat = self.category(cid)
        if not cat:
            raise KeyError(cid)
        return cat

    def delete_category(self, cid: str, reassign_to: str | None) -> int:
        if reassign_to and not self.category(reassign_to):
            raise ValueError("Target category does not exist")
        with self.db.tx() as conn:
            moved = conn.execute("UPDATE ideas SET category_id=?, updated_at=? WHERE category_id=?",
                                 (reassign_to, utcnow(), cid)).rowcount
            conn.execute("DELETE FROM categories WHERE id=?", (cid,))
        return moved

    # ----------------------------------------------------------------- ideas
    def idea(self, idea_id: str) -> dict[str, Any] | None:
        row = _row(self.db.connection().execute(
            "SELECT i.*, c.name AS category_name FROM ideas i LEFT JOIN categories c ON c.id=i.category_id WHERE i.id=?",
            (idea_id,)).fetchone())
        if row:
            self._hydrate(row)
        return row

    def _hydrate(self, row: dict[str, Any]) -> None:
        row["trips"] = _rows(self.db.connection().execute(
            "SELECT t.id, t.name FROM idea_trips it JOIN trips t ON t.id=it.trip_id WHERE it.idea_id=? ORDER BY t.name",
            (row["id"],)))
        for key in ("analysis_json", "metadata_json", "media_json"):
            raw = row.get(key)
            row[key[:-5]] = json.loads(raw) if raw else None
            row.pop(key, None)
        try:
            row["tags"] = json.loads(row.pop("tags_json") or "[]")
        except ValueError:
            row["tags"] = []
        row["has_thumbnail"] = bool((row.get("cover_path") and Path(row["cover_path"]).is_file()) or (row.get("thumbnail_path") and Path(row["thumbnail_path"]).is_file()))
        row["playable"] = bool(row.get("playback_path") and Path(row["playback_path"]).is_file() and row.get("media_status") == "ok")
        row["timed_notes"] = _rows(self.db.connection().execute(
            "SELECT id, t, text, created_at FROM timed_notes WHERE idea_id=? ORDER BY t", (row["id"],)))
        row["attachments"] = _rows(self.db.connection().execute(
            "SELECT id, kind, filename, created_at FROM attachments WHERE idea_id=? ORDER BY created_at", (row["id"],)))

    def find_by_normalized(self, normalized: str) -> dict[str, Any] | None:
        return _row(self.db.connection().execute(
            "SELECT * FROM ideas WHERE normalized_url=? AND deleted_at IS NULL ORDER BY created_at LIMIT 1",
            (normalized,)).fetchone())

    def create_idea(self, original_url: str, *, shared_text: str | None = None, source: str = "manual",
                    device_id: str | None = None, captured_at: str | None = None,
                    allow_duplicate: bool = False, normalized_override: str | None = None, **fields: Any) -> tuple[dict[str, Any], bool]:
        """Returns (idea, created). When a non-deleted idea with the same normalized URL
        exists and allow_duplicate is False, that idea is returned with created=False."""
        original_url = original_url.strip()
        if source != "local" and not is_safe_url(original_url):
            raise ValueError("Only http(s) URLs up to 2048 characters are accepted")
        normalized = normalized_override or normalize_url(original_url)
        existing = self.find_by_normalized(normalized)
        if existing and not allow_duplicate:
            return self.idea(existing["id"]), False  # type: ignore[return-value]
        now = utcnow()
        iid = new_id()
        cols = {
            "id": iid, "original_url": original_url, "normalized_url": normalized,
            "shared_text": shared_text, "source": source, "device_id": device_id,
            "captured_at": captured_at or now, "created_at": now, "updated_at": now,
            "duplicate_of": existing["id"] if existing else None,
        }
        for k, v in fields.items():
            if k in IDEA_EDITABLE and v is not None:
                cols[k] = v
        if cols.get("status") not in STATUSES:
            cols["status"] = "To Make"
        placeholders = ", ".join("?" for _ in cols)
        with self.db.tx() as conn:
            conn.execute(f"INSERT INTO ideas({', '.join(cols)}) VALUES ({placeholders})", tuple(cols.values()))
        return self.idea(iid), True  # type: ignore[return-value]

    def update_idea(self, idea_id: str, fields: dict[str, Any], *, expected_updated_at: str | None = None) -> dict[str, Any]:
        clean = {k: v for k, v in fields.items() if k in IDEA_EDITABLE}
        if "status" in clean and clean["status"] not in STATUSES:
            raise ValueError(f"Status must be one of {STATUSES}")
        if "category_id" in clean and clean["category_id"] and not self.category(clean["category_id"]):
            raise ValueError("Unknown category")
        if "canonical_url" in clean and clean["canonical_url"] and not is_safe_url(clean["canonical_url"]):
            raise ValueError("Canonical URL must be http(s)")
        if "finished_video_url" in clean and clean["finished_video_url"] and not is_safe_url(clean["finished_video_url"]):
            raise ValueError("Finished video link must be http(s)")
        if "tags" in fields:
            tags = fields["tags"]
            if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
                raise ValueError("tags must be a list of strings")
            clean["tags_json"] = json.dumps([t.strip()[:40] for t in dict.fromkeys(x.strip().lower() for x in tags if x.strip())])
        with self.db.tx() as conn:
            row = conn.execute("SELECT updated_at FROM ideas WHERE id=? AND deleted_at IS NULL", (idea_id,)).fetchone()
            if not row:
                raise KeyError(idea_id)
            if expected_updated_at and row["updated_at"] > expected_updated_at:
                raise ConflictError("The idea changed since it was loaded; reload and try again")
            if clean:
                sets = ", ".join(f"{k}=?" for k in clean)
                conn.execute(f"UPDATE ideas SET {sets}, updated_at=? WHERE id=?",
                             (*clean.values(), utcnow(), idea_id))
        return self.idea(idea_id)  # type: ignore[return-value]

    def set_internal(self, idea_id: str, **fields: Any) -> None:
        """Updates non-user fields (metadata/download/analysis state) without touching user edits."""
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.db.tx() as conn:
            conn.execute(f"UPDATE ideas SET {sets}, updated_at=? WHERE id=?", (*fields.values(), utcnow(), idea_id))

    def delete_idea(self, idea_id: str) -> None:
        with self.db.tx() as conn:
            conn.execute("UPDATE ideas SET deleted_at=?, updated_at=? WHERE id=?", (utcnow(), utcnow(), idea_id))

    def restore_idea(self, idea_id: str) -> None:
        with self.db.tx() as conn:
            conn.execute("UPDATE ideas SET deleted_at=NULL, updated_at=? WHERE id=?", (utcnow(), idea_id))

    def list_ideas(self, *, q: str = "", status: str | None = None, priority: str | None = None,
                   category_id: str | None = None, trip_id: str | None = None, inbox: bool = False,
                   download_status: str | None = None, captured_from: str | None = None,
                   captured_to: str | None = None, limit: int = 500, offset: int = 0,
                   sort: str = "captured_at", order: str = "desc", tag: str | None = None, playable: bool = False) -> list[dict[str, Any]]:
        where = ["i.deleted_at IS NULL"]
        params: list[Any] = []
        if q:
            like = f"%{q.strip()}%"
            where.append("(i.title LIKE ? OR i.caption LIKE ? OR i.notes LIKE ? OR i.creator LIKE ? OR i.original_url LIKE ? OR i.shooting_notes LIKE ? OR i.editing_notes LIKE ? OR i.tags_json LIKE ?)")
            params += [like] * 8
        if tag:
            where.append("i.tags_json LIKE ?"); params.append(f'%"{tag.strip().lower()}"%')
        if playable:
            where.append("i.playback_path IS NOT NULL AND i.media_status='ok'")
        if status:
            where.append("i.status=?"); params.append(status)
        if priority:
            where.append("i.priority=?"); params.append(priority)
        if category_id:
            where.append("i.category_id=?"); params.append(category_id)
        if trip_id:
            where.append("EXISTS (SELECT 1 FROM idea_trips it WHERE it.idea_id=i.id AND it.trip_id=?)"); params.append(trip_id)
        if inbox:
            where.append("NOT EXISTS (SELECT 1 FROM idea_trips it WHERE it.idea_id=i.id)")
        if download_status:
            where.append("i.download_status=?"); params.append(download_status)
        if captured_from:
            where.append("i.captured_at>=?"); params.append(captured_from)
        if captured_to:
            where.append("i.captured_at<=?"); params.append(captured_to + ("T99" if len(captured_to) == 10 else ""))
        sort_col = {"captured_at": "i.captured_at", "updated_at": "i.updated_at", "title": "i.title",
                    "priority": "i.priority", "status": "i.status"}.get(sort, "i.captured_at")
        direction = "ASC" if order.lower() == "asc" else "DESC"
        sql = (
            "SELECT i.*, c.name AS category_name FROM ideas i LEFT JOIN categories c ON c.id=i.category_id "
            f"WHERE {' AND '.join(where)} ORDER BY {sort_col} {direction}, i.created_at DESC LIMIT ? OFFSET ?"
        )
        params += [max(1, min(limit, 2000)), max(0, offset)]
        rows = _rows(self.db.connection().execute(sql, params))
        for r in rows:
            self._hydrate(r)
        return rows

    def counts(self) -> dict[str, int]:
        conn = self.db.connection()
        def one(sql: str, *p: Any) -> int:
            return int(conn.execute(sql, p).fetchone()[0])
        return {
            "inbox": one("SELECT COUNT(*) FROM ideas i WHERE deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM idea_trips it WHERE it.idea_id=i.id)"),
            "all": one("SELECT COUNT(*) FROM ideas WHERE deleted_at IS NULL"),
            "high": one("SELECT COUNT(*) FROM ideas WHERE deleted_at IS NULL AND priority='High' AND status<>'Published'"),
            "published": one("SELECT COUNT(*) FROM ideas WHERE deleted_at IS NULL AND status='Published'"),
            "trips": one("SELECT COUNT(*) FROM trips WHERE archived=0"),
            "metadata_pending": one("SELECT COUNT(*) FROM ideas WHERE deleted_at IS NULL AND metadata_status IN ('pending','fetching')"),
        }

    # ------------------------------------------------------------- timed notes
    def add_timed_note(self, idea_id: str, t: float, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("Note text is required")
        nid = new_id(); now = utcnow()
        with self.db.tx() as conn:
            if not conn.execute("SELECT 1 FROM ideas WHERE id=?", (idea_id,)).fetchone():
                raise KeyError(idea_id)
            conn.execute("INSERT INTO timed_notes(id, idea_id, t, text, created_at, updated_at) VALUES (?,?,?,?,?,?)", (nid, idea_id, max(0.0, float(t)), text[:2000], now, now))
            conn.execute("UPDATE ideas SET updated_at=? WHERE id=?", (now, idea_id))
        return {"id": nid, "idea_id": idea_id, "t": max(0.0, float(t)), "text": text[:2000], "created_at": now}

    def update_timed_note(self, note_id: str, t: float | None, text: str | None) -> None:
        with self.db.tx() as conn:
            if t is not None:
                conn.execute("UPDATE timed_notes SET t=?, updated_at=? WHERE id=?", (max(0.0, float(t)), utcnow(), note_id))
            if text is not None:
                conn.execute("UPDATE timed_notes SET text=?, updated_at=? WHERE id=?", (text.strip()[:2000], utcnow(), note_id))

    def delete_timed_note(self, note_id: str) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM timed_notes WHERE id=?", (note_id,))

    def recent_trips(self, limit: int = 5) -> list[dict[str, Any]]:
        return _rows(self.db.connection().execute(
            "SELECT t.id, t.name FROM trips t LEFT JOIN idea_trips it ON it.trip_id=t.id WHERE t.archived=0 "
            "GROUP BY t.id ORDER BY MAX(COALESCE(it.added_at, t.updated_at)) DESC LIMIT ?", (limit,)))

    def add_ideas_to_trip(self, idea_ids: list[str], trip_id: str) -> int:
        n = 0
        with self.db.tx() as conn:
            if not conn.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
                raise KeyError(trip_id)
            for iid in dict.fromkeys(idea_ids):
                if conn.execute("SELECT 1 FROM ideas WHERE id=? AND deleted_at IS NULL", (iid,)).fetchone():
                    cur = conn.execute("INSERT OR IGNORE INTO idea_trips(idea_id, trip_id, added_at) VALUES (?,?,?)", (iid, trip_id, utcnow()))
                    n += cur.rowcount
                    conn.execute("UPDATE ideas SET updated_at=? WHERE id=?", (utcnow(), iid))
        return n

    def remove_idea_from_trip(self, idea_id: str, trip_id: str) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM idea_trips WHERE idea_id=? AND trip_id=?", (idea_id, trip_id))
            conn.execute("UPDATE ideas SET updated_at=? WHERE id=?", (utcnow(), idea_id))

    def all_tags(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for r in self.db.connection().execute("SELECT tags_json FROM ideas WHERE deleted_at IS NULL"):
            try:
                for t in json.loads(r[0] or "[]"):
                    counts[t] = counts.get(t, 0) + 1
            except ValueError:
                pass
        return [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    # ------------------------------------------------------------------ trips
    def trips(self, include_archived: bool = False) -> list[dict[str, Any]]:
        sql = ("SELECT t.*, (SELECT COUNT(*) FROM idea_trips it JOIN ideas i ON i.id=it.idea_id WHERE it.trip_id=t.id AND i.deleted_at IS NULL) AS idea_count "
               "FROM trips t" + ("" if include_archived else " WHERE archived=0") + " ORDER BY archived, name")
        rows = _rows(self.db.connection().execute(sql))
        for r in rows:
            r["checklist"] = json.loads(r.pop("checklist_json") or "[]")
        return rows

    def trip(self, trip_id: str) -> dict[str, Any] | None:
        row = _row(self.db.connection().execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone())
        if row:
            row["checklist"] = json.loads(row.pop("checklist_json") or "[]")
            row["ideas"] = self.list_ideas(trip_id=trip_id, limit=2000)
        return row

    def create_trip(self, name: str, **fields: Any) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Trip name is required")
        now = utcnow()
        tid = new_id()
        with self.db.tx() as conn:
            conn.execute(
                "INSERT INTO trips(id, name, description, location, start_date, end_date, notes, checklist_json, archived, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (tid, name, fields.get("description") or "", fields.get("location") or "", fields.get("start_date"),
                 fields.get("end_date"), fields.get("notes") or "", json.dumps(fields.get("checklist") or []), 0, now, now))
        return self.trip(tid)  # type: ignore[return-value]

    def update_trip(self, trip_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {"name", "description", "location", "start_date", "end_date", "notes", "archived"}
        clean = {k: v for k, v in fields.items() if k in allowed}
        if "name" in clean and not str(clean["name"]).strip():
            raise ValueError("Trip name is required")
        if "archived" in clean:
            clean["archived"] = 1 if clean["archived"] else 0
        if "checklist" in fields:
            clean["checklist_json"] = json.dumps(fields["checklist"] or [])
        with self.db.tx() as conn:
            if not conn.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
                raise KeyError(trip_id)
            if clean:
                sets = ", ".join(f"{k}=?" for k in clean)
                conn.execute(f"UPDATE trips SET {sets}, updated_at=? WHERE id=?", (*clean.values(), utcnow(), trip_id))
        return self.trip(trip_id)  # type: ignore[return-value]

    def delete_trip(self, trip_id: str) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM trips WHERE id=?", (trip_id,))

    def set_idea_trips(self, idea_id: str, trip_ids: list[str]) -> dict[str, Any]:
        with self.db.tx() as conn:
            if not conn.execute("SELECT 1 FROM ideas WHERE id=?", (idea_id,)).fetchone():
                raise KeyError(idea_id)
            conn.execute("DELETE FROM idea_trips WHERE idea_id=?", (idea_id,))
            for tid in dict.fromkeys(trip_ids):
                if conn.execute("SELECT 1 FROM trips WHERE id=?", (tid,)).fetchone():
                    conn.execute("INSERT INTO idea_trips(idea_id, trip_id, added_at) VALUES (?,?,?)", (idea_id, tid, utcnow()))
            conn.execute("UPDATE ideas SET updated_at=? WHERE id=?", (utcnow(), idea_id))
        return self.idea(idea_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------- sync
    def receive_captures(self, device_id: str, device_name: str, captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        now = utcnow()
        with self.db.tx() as conn:
            conn.execute(
                "INSERT INTO devices(device_id, name, first_seen_at, last_seen_at) VALUES (?,?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET last_seen_at=excluded.last_seen_at, name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE devices.name END",
                (device_id, device_name or "", now, now))
        for cap in captures:
            capture_id = str(cap.get("capture_id") or "").strip()
            if not capture_id:
                results.append({"capture_id": "", "result": "invalid", "error": "capture_id missing"})
                continue
            receipt = _row(self.db.connection().execute("SELECT * FROM capture_receipts WHERE capture_id=?", (capture_id,)).fetchone())
            if receipt:
                results.append({"capture_id": capture_id, "result": receipt["result"], "idea_id": receipt["idea_id"], "replayed": True})
                continue
            shared_text = str(cap.get("shared_text") or "")
            url = (cap.get("url") or extract_url(shared_text) or "").strip()
            if not url or not is_safe_url(url):
                self._receipt(capture_id, device_id, None, "invalid")
                results.append({"capture_id": capture_id, "result": "invalid", "error": "no http(s) URL in shared content"})
                continue
            idea, created = self.create_idea(url, shared_text=shared_text or None, source="android",
                                             device_id=device_id, captured_at=cap.get("captured_at") or None,
                                             title=str(cap.get("title") or "") or None)
            result = "created" if created else "duplicate"
            self._receipt(capture_id, device_id, idea["id"], result)
            with self.db.tx() as conn:
                conn.execute("UPDATE devices SET captures_received=captures_received+1 WHERE device_id=?", (device_id,))
            results.append({"capture_id": capture_id, "result": result, "idea_id": idea["id"]})
        return results

    def _receipt(self, capture_id: str, device_id: str, idea_id: str | None, result: str) -> None:
        with self.db.tx() as conn:
            conn.execute("INSERT OR IGNORE INTO capture_receipts(capture_id, device_id, idea_id, result, received_at) VALUES (?,?,?,?,?)",
                         (capture_id, device_id, idea_id, result, utcnow()))

    def devices(self) -> list[dict[str, Any]]:
        return _rows(self.db.connection().execute("SELECT * FROM devices ORDER BY last_seen_at DESC"))

    # ------------------------------------------------------------- attachments
    def add_attachment(self, idea_id: str, kind: str, filename: str, path: str) -> dict[str, Any]:
        aid = new_id()
        with self.db.tx() as conn:
            conn.execute("INSERT INTO attachments(id, idea_id, kind, filename, path, created_at) VALUES (?,?,?,?,?,?)",
                         (aid, idea_id, kind, filename, path, utcnow()))
        return {"id": aid, "idea_id": idea_id, "kind": kind, "filename": filename, "path": path}

    def attachment(self, att_id: str) -> dict[str, Any] | None:
        return _row(self.db.connection().execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone())

    def delete_attachment(self, att_id: str) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM attachments WHERE id=?", (att_id,))


class ConflictError(Exception):
    pass
