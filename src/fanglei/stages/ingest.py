"""Input validation and source normalization."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fanglei.artifacts import atomic_write_json, atomic_write_text, sha256_text
from fanglei.errors import EmptyInputError, InputPathError
from fanglei.models import InputInfo, RunManifest, StageState
from fanglei.paths import allocate_run_dir


SUPPORTED_SUFFIXES = {".txt": "text", ".md": "markdown"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n")).strip()
    if not normalized:
        raise EmptyInputError("Input is empty")
    return normalized + "\n"


def _title_from_text(value: str, input_type: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if input_type == "markdown":
        for line in lines:
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                if title:
                    return title
    for line in lines:
        title = line.lstrip("#").strip()[:120]
        if title:
            return title
    return "Untitled Source"


def _source_document(
    *, run_id: str, input_type: str, display_name: str, ingested_at: str, content_hash: str, title: str, text: str
) -> str:
    return (
        "---\n"
        'schema_version: "1.0"\n'
        f"run_id: {run_id}\n"
        f"input_type: {input_type}\n"
        f"display_name: {display_name}\n"
        f"ingested_at: {ingested_at}\n"
        f"content_sha256: {content_hash}\n"
        f"title: {title}\n"
        "---\n\n"
        f"{text}"
    )


def _create_run(*, value: str, runs_dir: Path, input_type: str, display_name: str) -> Path:
    text = normalize_text(value)
    title = _title_from_text(text, input_type)
    run_dir = allocate_run_dir(runs_dir, title)
    timestamp = _now()
    content_hash = sha256_text(text)
    source = _source_document(
        run_id=run_dir.name,
        input_type=input_type,
        display_name=display_name,
        ingested_at=timestamp,
        content_hash=content_hash,
        title=title,
        text=text,
    )
    atomic_write_text(run_dir / "source.md", source)
    manifest = RunManifest(
        run_id=run_dir.name,
        created_at=timestamp,
        updated_at=timestamp,
        input=InputInfo(type=input_type, display_name=display_name, sha256=content_hash),
        stages={
            "ingest": StageState(
                status="succeeded",
                attempts=1,
                input_sha256=content_hash,
                output_sha256=sha256_text(source),
                started_at=timestamp,
                finished_at=timestamp,
            ),
            "analyze": StageState(),
        },
    )
    atomic_write_json(run_dir / "run.json", manifest.model_dump(mode="json"))
    return run_dir


def ingest_file(path: Path, runs_dir: Path) -> Path:
    path = Path(path)
    if not path.is_file():
        raise InputPathError(f"Input file not found: {path}")
    input_type = SUPPORTED_SUFFIXES.get(path.suffix.lower())
    if input_type is None:
        raise InputPathError("Only .txt and .md files are supported")
    try:
        value = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputPathError(f"Input file must be UTF-8: {path}") from error
    return _create_run(value=value, runs_dir=Path(runs_dir), input_type=input_type, display_name=path.name)


def ingest_text(text: str, runs_dir: Path) -> Path:
    return _create_run(value=text, runs_dir=Path(runs_dir), input_type="text", display_name="pasted-text")
