"""Safe run-directory naming and resolution."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from fanglei.errors import RunPathError


RUN_ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{3}-[a-z0-9][a-z0-9-]*$")


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug[:60].rstrip("-") or "topic"


def allocate_run_dir(runs_dir: Path, title: str) -> Path:
    date_prefix = datetime.now().astimezone().date().isoformat()
    slug = slugify(title)
    runs_dir.mkdir(parents=True, exist_ok=True)
    for sequence in range(1, 1000):
        if any(runs_dir.glob(f"{date_prefix}-{sequence:03d}-*")):
            continue
        candidate = runs_dir / f"{date_prefix}-{sequence:03d}-{slug}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RunPathError(f"No run ID available for {date_prefix}")


def resolve_run_dir(runs_dir: Path, run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RunPathError(f"Invalid run ID: {run_id}")
    root = runs_dir.resolve()
    candidate = (root / run_id).resolve()
    if candidate.parent != root or not candidate.is_dir():
        raise RunPathError(f"Run not found: {run_id}")
    return candidate
