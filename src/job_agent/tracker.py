"""CSV application tracker. New jobs are added; your edits to existing rows are never overwritten."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

TRACKER = Path("data/tracker.csv")
COLUMNS = [
    "id",
    "found_on",
    "fit_score",
    "title",
    "company",
    "location",
    "salary",
    "url",
    "source",
    "matched_skills",
    "gaps",
    "pitch",
    "status",
    "notes",
]
STATUSES = ["new", "applied", "interviewing", "offer", "rejected", "skipped"]


def load(path: Path = TRACKER) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, dtype=str).fillna("")
    return pd.DataFrame(columns=COLUMNS)


def upsert(rows: list[dict], path: Path = TRACKER) -> tuple[pd.DataFrame, int]:
    """Append rows whose id is not tracked yet. Returns the tracker and the number added."""
    current = load(path)
    known = set(current["id"])
    fresh = [
        {**r, "found_on": date.today().isoformat(), "status": "new", "notes": ""}
        for r in rows
        if r["id"] not in known
    ]
    if fresh:
        current = pd.concat([current, pd.DataFrame(fresh)], ignore_index=True)
    current = current.reindex(columns=COLUMNS).fillna("")
    path.parent.mkdir(parents=True, exist_ok=True)
    current.to_csv(path, index=False)
    return current, len(fresh)
