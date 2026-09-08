"""Question extraction and research-brief generation."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from fanglei.artifacts import atomic_write_json, atomic_write_text, read_json, sha256_text
from fanglei.errors import ArtifactConflictError, ProviderError
from fanglei.models import AnalysisResult, ProviderInfo, RunManifest, StageError, StageState
from fanglei.paths import resolve_run_dir
from fanglei.providers.base import AnalysisProvider


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_source(document: str) -> tuple[str, str]:
    parts = document.split("---\n", 2)
    if len(parts) != 3:
        raise ArtifactConflictError("source.md has an invalid metadata header")
    metadata, body = parts[1], parts[2].lstrip("\n")
    title = next((line.removeprefix("title:").strip() for line in metadata.splitlines() if line.startswith("title:")), "")
    if not title or not body.strip():
        raise ArtifactConflictError("source.md is missing a title or body")
    return title, body


def _fingerprint(source_document: str, provider: AnalysisProvider) -> str:
    value = json.dumps(
        {"source_sha256": sha256_text(source_document), "provider": provider.name, "prompt_version": provider.prompt_version},
        sort_keys=True,
    )
    return sha256_text(value)


def _outputs_match(run_dir: Path, output_hashes: str | dict[str, str] | None) -> bool:
    if not isinstance(output_hashes, dict):
        return False
    for name in ("questions.json", "research.md"):
        path = run_dir / name
        if not path.is_file():
            return False
        try:
            actual_hash = sha256_text(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            return False
        if output_hashes.get(name) != actual_hash:
            return False
    return True


def _snapshot_outputs(run_dir: Path, attempt: int) -> None:
    existing = [run_dir / name for name in ("questions.json", "research.md") if (run_dir / name).is_file()]
    if not existing:
        return
    history_root = run_dir / ".history" / "analyze"
    sequence = max(attempt, 1)
    snapshot = history_root / f"attempt-{sequence:03d}"
    while snapshot.exists():
        sequence += 1
        snapshot = history_root / f"attempt-{sequence:03d}"
    snapshot.mkdir(parents=True)
    for path in existing:
        shutil.copy2(path, snapshot / path.name)


def _render_research(result: AnalysisResult) -> str:
    lines = [
        "# Research Brief",
        "",
        "## 核心主题",
        "",
        result.core_topic,
        "",
    ]
    for index, question in enumerate(result.research_questions, start=1):
        lines.extend(
            [
                f"## 研究问题 {index}：{question.question}",
                "",
                "### 为什么要研究",
                "",
                question.purpose,
                "",
                "### 原文提供的线索",
                "",
            ]
        )
        clues = list(
            dict.fromkeys(
                [fact.statement for fact in result.key_facts]
                + [argument.claim for argument in result.author_arguments]
            )
        )
        lines.extend([f"- {clue}" for clue in clues] or ["- 原文未提供可直接识别的事实线索。"])
        lines.extend(["", "### 需要验证的主张", ""])
        lines.extend(
            [f"- [ ] {claim.id}：{claim.claim}" for claim in result.claims_requiring_external_verification]
            or ["- [ ] 尚未识别到明确的事实性主张，仍需外部检索确认。"]
        )
        lines.extend(["", "### 建议检索的独立来源", ""])
        lines.extend([f"- {source_type}" for source_type in question.expected_source_types])
        lines.extend(
            [
                "",
                "### 当前可形成的假设",
                "",
                "原文仅用于提出研究方向；结论需在多来源证据收集后形成。",
                "",
                "### 当前证据状态",
                "",
                "未进行外部事实核查，不得作为已验证结论进入视频脚本。",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def analyze_run(
    run_id: str,
    runs_dir: Path,
    provider: AnalysisProvider,
    force: bool = False,
) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest_path = run_dir / "run.json"
    source_path = run_dir / "source.md"
    try:
        manifest = RunManifest.model_validate(read_json(manifest_path))
        source_document = source_path.read_text(encoding="utf-8")
        ingest_state = manifest.stages["ingest"]
        previous = manifest.stages["analyze"]
        fingerprint = _fingerprint(source_document, provider)
    except (OSError, UnicodeError, ValueError, KeyError) as error:
        raise ArtifactConflictError(f"Unable to load run.json or source.md: {error}") from error
    if (
        ingest_state.status != "succeeded"
        or not isinstance(ingest_state.output_sha256, str)
        or ingest_state.output_sha256 != sha256_text(source_document)
    ):
        error = ArtifactConflictError("source.md does not match the recorded ingest hash; create a new run")
        failed_at = _now()
        manifest.status = "failed"
        manifest.updated_at = failed_at
        manifest.stages["analyze"] = StageState(
            status="failed",
            attempts=previous.attempts + 1,
            input_sha256=fingerprint,
            provider=provider.name,
            prompt_version=provider.prompt_version,
            started_at=failed_at,
            finished_at=failed_at,
            error=StageError(code="ARTIFACT_CONFLICT", message=str(error)),
        )
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
        raise error

    if previous.status == "succeeded" and previous.input_sha256 == fingerprint:
        if _outputs_match(run_dir, previous.output_sha256):
            if not force:
                return run_dir
        elif not force:
            raise ArtifactConflictError("Analyze outputs were modified; use --force to replace them")
    elif previous.status == "succeeded" and not force:
        raise ArtifactConflictError("Analyze inputs changed; use --force to replace existing outputs")

    if force:
        _snapshot_outputs(run_dir, previous.attempts)

    started_at = _now()
    attempts = previous.attempts + 1
    manifest.stages["analyze"] = StageState(
        status="running",
        attempts=attempts,
        input_sha256=fingerprint,
        provider=provider.name,
        prompt_version=provider.prompt_version,
        started_at=started_at,
    )
    manifest.updated_at = started_at
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        title, source_body = _parse_source(source_document)
        result = provider.analyze(source_body, title)
        if not isinstance(result, AnalysisResult):
            result = AnalysisResult.model_validate(result)
        generated_at = _now()
        questions = {
            "schema_version": "1.0",
            "run_id": run_id,
            "provider": ProviderInfo(
                name=provider.name,
                model=None,
                prompt_version=provider.prompt_version,
            ).model_dump(mode="json"),
            "source_sha256": sha256_text(source_document),
            **result.model_dump(mode="json"),
            "generated_at": generated_at,
        }
        research = _render_research(result)
        atomic_write_json(run_dir / "questions.json", questions)
        atomic_write_text(run_dir / "research.md", research)
    except ArtifactConflictError as error:
        failed_at = _now()
        manifest.status = "failed"
        manifest.updated_at = failed_at
        manifest.stages["analyze"] = StageState(
            status="failed",
            attempts=attempts,
            input_sha256=fingerprint,
            provider=provider.name,
            prompt_version=provider.prompt_version,
            started_at=started_at,
            finished_at=failed_at,
            error=StageError(code="ARTIFACT_CONFLICT", message=str(error)),
        )
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
        raise
    except Exception as error:
        failed_at = _now()
        manifest.status = "failed"
        manifest.updated_at = failed_at
        manifest.stages["analyze"] = StageState(
            status="failed",
            attempts=attempts,
            input_sha256=fingerprint,
            provider=provider.name,
            prompt_version=provider.prompt_version,
            started_at=started_at,
            finished_at=failed_at,
            error=StageError(code="PROVIDER_FAILED", message=str(error)),
        )
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
        raise ProviderError(f"Analysis provider failed: {error}") from error

    finished_at = _now()
    output_hashes = {
        name: sha256_text((run_dir / name).read_text(encoding="utf-8"))
        for name in ("questions.json", "research.md")
    }
    manifest.status = "analyzed"
    manifest.updated_at = finished_at
    manifest.stages["analyze"] = StageState(
        status="succeeded",
        attempts=attempts,
        input_sha256=fingerprint,
        output_sha256=output_hashes,
        provider=provider.name,
        prompt_version=provider.prompt_version,
        started_at=started_at,
        finished_at=finished_at,
    )
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    return run_dir
