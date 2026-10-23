"""Gentle reminders for High-priority ideas with a planned follow-up date.

Rules: reminders are off by default; an idea is due when its follow_up_date is today or
earlier, it is High priority, not Published, and it has not been reminded since it last
changed; a quiet period (hours) prevents repeats. Saving an idea never triggers a reminder.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import Database, utcnow


def due_ideas(db: Database, quiet_hours: int) -> list[dict[str, Any]]:
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(0, quiet_hours))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    rows = db.connection().execute(
        "SELECT id, title, original_url, follow_up_date, updated_at, reminded_at, reminded_for_updated_at FROM ideas "
        "WHERE deleted_at IS NULL AND priority='High' AND status<>'Published' AND follow_up_date IS NOT NULL "
        "AND follow_up_date<>'' AND follow_up_date<=? ORDER BY follow_up_date", (today,)).fetchall()
    due = []
    for r in rows:
        r = dict(r)
        if r["reminded_at"] and r["reminded_at"] > cutoff:
            continue
        if r["reminded_for_updated_at"] and r["reminded_for_updated_at"] == r["updated_at"]:
            continue
        due.append(r)
    return due


def mark_reminded(db: Database, idea_ids: list[str]) -> None:
    now = utcnow()
    with db.tx() as conn:
        for iid in idea_ids:
            conn.execute("UPDATE ideas SET reminded_at=?, reminded_for_updated_at=updated_at WHERE id=?", (now, iid))
