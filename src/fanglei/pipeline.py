"""V0.2 file-artifact research pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import atomic_write_bytes, atomic_write_json, read_json, sha256_bytes, sha256_text
from fanglei.errors import ArtifactConflictError
from fanglei.evidence_policy import is_claim_eligible_for_content
from fanglei.models import ArtifactState, RunManifest, StageError, StageState
from fanglei.paths import resolve_run_dir
from fanglei.providers.search import SearchProvider, SearchRequest
from fanglei.providers.document import FetchContext
from fanglei.research import (
    FetchedDocument,
    RuleBasedEvidenceExtractor,
    deduplicate_sources,
    extract_qualitative_primary_evidence,
    verify_claims,
    verify_claims_v22,
)
from fanglei.source_contract import (
    AuthoritativePrimarySetPolicyV1,
    build_sources_artifact_v21,
    parse_sources_artifact,
)
from fanglei.research_focus import ResearchFocusV1
from fanglei.publication_metadata import (
    PublicationDateReviewV1,
    apply_publication_date_reviews_to_index,
    validate_publication_date_review,
)
from fanglei.security import safe_error_message, sanitize_url
from fanglei.evidence_policy import gate_evidence
from fanglei.evidence_targets import (
    EvidenceTargetSetV1,
    build_authority_claim_proposals,
    parse_evidence_target_set,
)


class DocumentFetcher(Protocol):
    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument: ...


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load(
    run_dir: Path,
    *,
    human_angle_selection_mode: bool = False,
    evidence_targets_mode: bool = False,
) -> tuple[RunManifest, ArtifactRegistry]:
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    registry = ArtifactRegistry(
        run_dir,
        manifest,
        human_angle_selection_mode=human_angle_selection_mode,
        evidence_targets_mode=evidence_targets_mode,
    )
    for name, owner in (("source.md", "ingest"), ("questions.json", "analyze")):
        path = run_dir / name
        state = manifest.artifacts[name]
        if path.is_file() and state.status == "missing":
            timestamp = _now()
            state.status = "valid"
            state.content_hash = sha256_text(path.read_text(encoding="utf-8"))
            state.created_at = state.updated_at = timestamp
            state.owner = owner
            if name == "questions.json":
                state.dependencies = {"source.md": manifest.artifacts["source.md"].content_hash or ""}
    if "research_focus.json" in registry.graph:
        try:
            focus_path = run_dir / "research_focus.json"
            if not focus_path.is_file():
                raise ArtifactConflictError("registered research_focus.json is missing")
            focus = ResearchFocusV1.model_validate(registry.read_json("research_focus.json"))
            if focus.run_id != manifest.run_id:
                raise ValueError("research focus run_id does not match the run manifest")
            source_artifact = registry.read_json("sources.json")
            parsed_sources = parse_sources_artifact(source_artifact)
            source_policy = getattr(parsed_sources, "source_policy", None)
            if isinstance(source_policy, AuthoritativePrimarySetPolicyV1) and (
                source_policy.run_id != focus.run_id
                or source_policy.case_id != focus.case_id
                or parsed_sources.package_admissibility != "admissible"
            ):
                raise ValueError("research focus identity does not match its approved authority source package")
        except Exception as error:
            registry.save_manifest()
            raise ArtifactConflictError(f"invalid registered research_focus.json: {error}") from error
    registry.save_manifest()
    return manifest, registry


STAGE_ARTIFACT = {
    "search": "search_results.json",
    "source_fetch": "source_documents/index.json",
    "source_selection": "sources.json",
    "evidence_targets": "evidence_targets.json",
    "factcheck": "facts.json",
    "research_synthesis": "research.md",
    "angle_generation": "angles.json",
    "angle_selection": "angle.md",
    "human_angle_selection": "angle_selection.json",
    "script_generation": "script.json",
    "script_render": "script.md",
    "visual_planning": "visual_beats.json",
    "storyboard_generation": "storyboard.json",
    "visual_plan_render": "visual_plan.md",
    "narration_generation": "narration.json",
    "audio_generation": "audio/metadata.json",
    "audio_alignment": "alignment.json",
    "timeline_compilation": "timeline.json",
    "nikola_adaptation": "render_manifest.json",
    "render_preflight": "render_qa.json",
    "subtitle_generation": "subtitle_track.json",
    "audio_mastering": "audio_mastering.json",
    "v1b_render_adaptation": "render_manifest_v1b.json",
}

STAGE_ARTIFACTS = {
    "narration_generation": ("narration.json", "narration.txt"),
    "audio_generation": ("audio/narration.wav", "audio/metadata.json", "audio/quality.json"),
    "voice_review": ("audio/review.json",),
    "alignment_review": ("alignment_review.json",),
    "audio_alignment": ("alignment.json",),
    "timeline_compilation": ("timeline.json",),
    "nikola_adaptation": ("renderer_project", "render_manifest.json"),
    "render_preflight": ("preflight_report.json", "render_qa.json"),
    "subtitle_generation": ("subtitle_track.json",),
    "audio_mastering": ("audio/mastered_narration.wav", "audio_mastering.json"),
    "v1b_render_adaptation": ("renderer_project_v1b", "render_manifest_v1b.json"),
}


def _execute(manifest: RunManifest, registry: ArtifactRegistry, stage: str, action, force: bool = False) -> None:
    previous = manifest.stages.get(stage, StageState())
    artifact_names = STAGE_ARTIFACTS.get(stage, (STAGE_ARTIFACT[stage],))
    artifact_states = [manifest.artifacts[name] for name in artifact_names]
    if previous.status == "succeeded" and all(state.status == "valid" for state in artifact_states) and not force:
        try:
            for artifact_name in artifact_names:
                registry.validate(artifact_name)
            return
        except Exception:
            pass
    started = _now()
    manifest.stages[stage] = StageState(status="running", attempts=previous.attempts + 1, started_at=started)
    registry.save_manifest()
    try:
        action()
    except Exception as error:
        manifest.stages[stage] = StageState(
            status="failed", attempts=previous.attempts + 1, started_at=started, finished_at=_now(),
            error=StageError(code="STAGE_FAILED", message=safe_error_message(error)),
        )
        registry.save_manifest()
        raise
    manifest.stages[stage] = StageState(
        status="succeeded", attempts=previous.attempts + 1, started_at=started, finished_at=_now()
    )
    registry.save_manifest()


def _question_texts(questions: dict[str, Any]) -> list[str]:
    return [q["question"] for q in questions.get("research_questions", []) if q.get("question")]


def _documents_from_index(run_dir: Path, registry: ArtifactRegistry) -> tuple[dict[str, Any], list[FetchedDocument]]:
    try:
        document_index = registry.read_json("source_documents/index.json")
    except ArtifactConflictError:
        # Validation marks a changed capture/index stale in the in-memory manifest.
        # Persist that fail-closed state without writing any source artifact.
        registry.save_manifest()
        raise
    fields = FetchedDocument.__dataclass_fields__
    documents: list[FetchedDocument] = []
    for row in document_index.get("documents", []):
        values = {key: value for key, value in row.items() if key in fields}
        review_value = row.get("publication_date_review")
        if review_value is not None:
            normalized_path = run_dir / row.get("path", "")
            normalized_text = normalized_path.read_text(encoding="utf-8")
            review = validate_publication_date_review(
                review_value,
                source_id=row.get("source_id"),
                url=row.get("url"),
                source_text=normalized_text,
            )
            if row.get("published_at") != review.published_at:
                raise ValueError(f"reviewed publication date does not match index metadata for {row.get('source_id')}")
        for asset in row.get("files", []):
            asset_path = run_dir / asset.get("path", "")
            if asset.get("role") == "raw_response" and asset_path.suffix == ".json":
                values["raw_content"] = asset_path.read_text(encoding="utf-8")
            elif asset.get("role") == "raw_response" and asset_path.suffix == ".pdf":
                values["raw_bytes"] = asset_path.read_bytes()
        documents.append(FetchedDocument(**values))
    return document_index, documents


def _source_selection_artifact(
    run_id: str,
    registry: ArtifactRegistry,
    documents: list[FetchedDocument],
    *,
    source_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = deduplicate_sources(documents)
    if source_policy is None:
        independent_count = sum(row["counts_as_independent"] for row in rows)
        return {
            "schema_version": "2.0",
            "selection_status": "selected" if independent_count >= 3 else "insufficient_sources",
            "sources": rows,
        }
    document_index = registry.read_json("source_documents/index.json")
    policy_case_id = source_policy.get("case_id") if source_policy.get("name") == "authoritative_primary_set" else None
    return build_sources_artifact_v21(
        rows,
        documents=documents,
        document_index=document_index,
        run_id=run_id,
        case_id=policy_case_id,
        source_policy=source_policy,
    )


def apply_publication_date_reviews(
    run_id: str,
    runs_dir: Path,
    reviews: list[PublicationDateReviewV1 | Mapping[str, Any]],
) -> Path:
    """Apply explicit date reviews offline through the source-index owner."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    registry = ArtifactRegistry(run_dir, manifest)
    if manifest.run_id != run_id:
        raise ValueError("run manifest identity does not match the requested run")
    try:
        document_index = registry.read_json("source_documents/index.json")
    except ArtifactConflictError:
        registry.save_manifest()
        raise
    run_root = run_dir.resolve()
    source_root = (run_dir / "source_documents").resolve()
    if not source_root.is_relative_to(run_root):
        raise ValueError("source_documents directory resolves outside the run directory")
    normalized_text_by_source_id: dict[str, str] = {}
    for row in document_index.get("documents", []):
        source_id = row.get("source_id")
        relative = Path(row.get("path", ""))
        if not source_id or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source document index contains an unsafe normalized-text path or identity")
        normalized_path = (run_dir / relative).resolve()
        if not normalized_path.is_relative_to(source_root) or not normalized_path.is_file():
            raise ValueError(f"normalized source text is missing or outside source_documents for {source_id}")
        normalized_files = [
            asset for asset in row.get("files", [])
            if asset.get("role") == "normalized_text"
        ]
        if (
            len(normalized_files) != 1
            or normalized_files[0].get("path") != row.get("path")
            or normalized_files[0].get("content_hash") != row.get("content_hash")
        ):
            raise ValueError(f"normalized source text index entry is invalid for {source_id}")
        text = normalized_path.read_text(encoding="utf-8")
        if sha256_text(text) != row.get("content_hash"):
            raise ValueError(f"normalized source text hash does not match the index for {source_id}")
        normalized_text_by_source_id[source_id] = text

    rebuilt_index = apply_publication_date_reviews_to_index(
        document_index,
        reviews,
        normalized_text_by_source_id=normalized_text_by_source_id,
    )
    if rebuilt_index == document_index:
        return run_dir / "source_documents" / "index.json"
    registry.write_json("source_documents/index.json", rebuilt_index, "source_fetch", force=True)
    registry.save_manifest()
    return run_dir / "source_documents" / "index.json"


def rebuild_source_selection_from_index(
    run_id: str,
    runs_dir: Path,
    *,
    source_policy: Mapping[str, Any] | None = None,
) -> Path:
    """Rebuild only sources.json from the current local source-document index."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    if manifest.run_id != run_id:
        raise ValueError("run manifest identity does not match the requested run")
    _, documents = _documents_from_index(run_dir, registry)

    def select() -> None:
        artifact = _source_selection_artifact(
            run_id,
            registry,
            documents,
            source_policy=source_policy,
        )
        registry.write_json("sources.json", artifact, "source_selection", force=True)

    _execute(manifest, registry, "source_selection", select, force=True)
    return run_dir


def _search_requests(questions: dict[str, Any]) -> list[SearchRequest]:
    def values(value: Any) -> list[str]:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple)):
            candidates = [item for item in value if isinstance(item, str)]
        else:
            candidates = []
        return [item.strip() for item in candidates if item.strip()]

    shared_context = [
        *values(questions.get("core_topic")),
        *values(questions.get("entities")),
        *values(questions.get("measures")),
        *values(questions.get("periods")),
    ]
    intents: list[list[str]] = []
    for claim in questions.get("claims_requiring_external_verification", []):
        if not isinstance(claim, dict):
            continue
        intents.append([*values(claim.get("claim")), *values(claim.get("reason"))])
    for question in questions.get("research_questions", []):
        if not isinstance(question, dict):
            continue
        intents.append([
            *values(question.get("question")),
            *values(question.get("purpose")),
            *values(question.get("expected_source_types")),
        ])
    intents.extend([[item] for item in values(questions.get("subquestions"))])
    if not intents:
        intents = [[question] for question in _question_texts(questions)]
    if not intents:
        intents = [[]]

    requests: list[SearchRequest] = []
    seen_queries: set[str] = set()
    for intent in intents:
        query_parts = list(dict.fromkeys([*shared_context, *intent]))
        query = " ".join(query_parts).strip()
        normalized = " ".join(query.casefold().split())
        if not normalized or normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        requests.append(SearchRequest(query=query, max_results=12))
    return requests


def _fetch_context(questions: dict[str, Any]) -> FetchContext:
    text = " ".join([
        questions.get("core_topic", ""),
        *[item.get("claim", "") for item in questions.get("claims_requiring_external_verification", [])],
        *_question_texts(questions),
    ])
    def values(value: Any) -> list[str]:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple)):
            candidates = [item for item in value if isinstance(item, str)]
        else:
            candidates = []
        return [item.strip() for item in candidates if item.strip()]

    explicit_country = questions.get("country")
    country = explicit_country.strip() if isinstance(explicit_country, str) and explicit_country.strip() else None
    explicit_years = values(questions.get("years"))
    years = tuple(sorted(set(explicit_years or re.findall(r"(?:19|20)\d{2}", text))))
    indicators = tuple(dict.fromkeys(values(questions.get("indicators"))))
    return FetchContext(country=country, years=years, indicators=indicators, questions=tuple(_question_texts(questions)))


def _fetch_failure_code(error: BaseException) -> str:
    message = safe_error_message(error).lower()
    for code in (
        "dynamic_content_unavailable", "empty_body", "invalid_pdf", "pdf_size_limit",
        "pdf_page_limit", "pdf_text_limit", "pdf_encrypted", "pdf_no_extractable_text",
    ):
        if code in message:
            return code
    if "http 403" in message:
        return "access_denied"
    if "http 429" in message:
        return "rate_limited"
    if "timeout" in message:
        return "timeout"
    return "fetch_failed"


def _render_research(run_id: str, questions: list[str], sources: list[dict[str, Any]], facts: dict[str, Any]) -> str:
    """Render legacy Research output with its historical verified-only rule."""
    source_by_id = {s["source_id"]: s for s in sources}
    lines = ["# 多源研究报告", "", f"Run: `{run_id}`", "", "## 研究问题", ""]
    lines.extend(f"- {q}" for q in questions)
    lines.extend(["", "## 已核验事实", ""])
    verified = [c for c in facts["claims"] if c["verification_status"] == "verified"]
    if not verified:
        lines.append("- 当前没有达到多源核验门槛的事实。")
    for claim in verified:
        source_ids = list(dict.fromkeys(e["source_id"] for e in claim["evidence"]))
        lines.append(f"- {claim['claim_text']} `[{claim['claim_id']}; {', '.join(source_ids)}]`")
    lines.extend(["", "## 未确认或冲突", ""])
    unresolved = [c for c in facts["claims"] if c["verification_status"] != "verified"]
    lines.extend(f"- {c['claim_text']}（{c['verification_status']}；{c['claim_id']}）" for c in unresolved)
    lines.extend(["", "## 来源索引", ""])
    for source in sources:
        lines.append(f"- `{source['source_id']}` [{source['title']}]({source['url']})，可信度 {source['credibility_tier']}")
    lines.extend(["", "## 追溯说明", "", "重要陈述按 `claim_id → evidence → source_id → original URL` 追溯；搜索摘要不作为证据。", ""])
    return "\n".join(lines)


def _render_research_focus(
    run_id: str,
    focus: ResearchFocusV1,
    source_artifact: dict[str, Any],
    facts: dict[str, Any],
) -> str:
    """Render a focused, deterministic brief from allowed facts only."""
    sources = source_artifact.get("sources", [])
    policy = source_artifact.get("source_policy", {})
    document_metadata = {
        row["source_id"]: dict(row)
        for row in sources
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }
    source_order = {
        row["source_id"]: index
        for index, row in enumerate(sources)
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }
    approved_documents = policy.get("approved_documents", []) if isinstance(policy, dict) else []
    document_order: dict[str, int] = {}
    for index, row in enumerate(approved_documents):
        if isinstance(row, dict) and isinstance(row.get("source_id"), str):
            source_id = row["source_id"]
            document_order[source_id] = index
            document_metadata.setdefault(source_id, {}).update(row)
    claim_records = facts.get("claims", [])
    allowed_claims = [claim for claim in claim_records if is_claim_eligible_for_content(claim)]

    def role_group(claim: dict[str, Any]) -> tuple[str, ...]:
        attestation = claim.get("authority_attestation")
        source_ids = attestation.get("source_ids", []) if isinstance(attestation, dict) else []
        if not source_ids:
            source_ids = claim.get("source_ids", [])
        if not source_ids:
            source_ids = [
                evidence.get("source_id")
                for evidence in claim.get("evidence", [])
                if isinstance(evidence, dict) and isinstance(evidence.get("source_id"), str)
            ]
        source_ids = list(dict.fromkeys(source_id for source_id in source_ids if isinstance(source_id, str)))
        source_ids.sort(
            key=lambda source_id: (
                0,
                document_order[source_id],
                source_id,
            ) if source_id in document_order else (
                1,
                source_order.get(source_id, len(source_order)),
                source_id,
            )
        )
        roles: list[str] = []
        for source_id in source_ids:
            metadata = document_metadata.get(source_id, {})
            role = metadata.get("evidence_role") or metadata.get("source_type") or metadata.get("title")
            role = " ".join(role.split()) if isinstance(role, str) else ""
            roles.append(role or f"source:{source_id}")
        return tuple(dict.fromkeys(roles)) or ("source role not recorded",)

    grouped_claims: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for claim in allowed_claims:
        grouped_claims.setdefault(role_group(claim), []).append(claim)

    def render_claim(claim: dict[str, Any]) -> list[str]:
        source_ids = list(dict.fromkeys(claim.get("source_ids", [])))
        lines = [f"- {claim['claim_text']} `[{claim['claim_id']}; {', '.join(source_ids)}]`"]
        for evidence in claim.get("evidence", []):
            if evidence.get("relation") != "supports" or not evidence.get("evidence_eligible", True):
                continue
            evidence_text = evidence.get("evidence_text", "")
            proposition_span = evidence.get("proposition_span")
            if proposition_span is not None:
                from fanglei.evidence_targets import validate_proposition_span

                parsed_span = validate_proposition_span(evidence_text, proposition_span)
                if parsed_span is None:
                    # A malformed proposition binding cannot fall back to the
                    # larger evidence excerpt in substantive Research output.
                    continue
                evidence_text = str(parsed_span["text"])
            locator = evidence.get("paragraph_locator") or evidence.get("source_section") or "source excerpt"
            lines.append(f"  - Evidence ({evidence.get('source_id')}, {locator}): “{evidence_text}”")
        return lines

    lines = [
        "# Research Brief",
        "",
        f"Run: `{run_id}`",
        "",
        "## Locked research question",
        "",
        focus.primary_question,
        "",
        "## Research subquestions",
        "",
    ]
    lines.extend(f"{index}. {question}" for index, question in enumerate(focus.subquestions, start=1))
    lines.extend(["", "## Evidence-grounded findings", ""])
    if not grouped_claims:
        lines.append("- No verified facts currently satisfy the downstream eligibility rule.")
    for index, (roles, claims) in enumerate(grouped_claims.items(), start=1):
        lines.extend([f"### Evidence group {index}", "", f"Document roles: {'; '.join(roles)}", ""])
        lines.extend(line for claim in claims for line in render_claim(claim))
    lines.extend([
        "",
        "## Evidence boundary",
        "",
        "Substantive findings below use only claim records with `verification_status=verified` and `allowed_downstream=true`. "
        "Source-package approval does not itself verify a claim. Preserve each claim’s recorded attribution and scope; "
        "do not infer causality beyond its evidence.",
        "",
        "## Framing constraints",
        "",
    ])
    lines.extend(f"- {constraint}" for constraint in focus.constraints)
    excluded = [claim for claim in claim_records if not is_claim_eligible_for_content(claim)]
    lines.extend(["", "## Excluded fact records", ""])
    lines.append(
        f"{len(excluded)} records were not used as substantive assertions because they are unverified "
        "or not allowed downstream."
    )
    lines.extend(["", "## Source index", ""])
    for source in sources:
        lines.append(
            f"- `{source['source_id']}` [{source['title']}]({source['url']})，可信度 {source.get('credibility_tier', 'not recorded')}"
        )
    lines.extend([
        "",
        "## Traceability",
        "",
        "Substantive statements are limited to facts with `verification_status=verified` and `allowed_downstream=true`; "
        "trace each through `claim_id → evidence → source_id → original URL`.",
        "",
    ])
    return "\n".join(lines)


def run_v02_pipeline(
    run_id: str,
    runs_dir: Path,
    search_provider: SearchProvider,
    fetcher: DocumentFetcher,
    *,
    stop_after: str | None = None,
    force_stage: str | None = None,
    source_policy: Mapping[str, Any] | None = None,
    authority_claims: Mapping[str, Mapping[str, Any]] | None = None,
    evidence_targets: EvidenceTargetSetV1 | Mapping[str, object] | None = None,
) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    if evidence_targets is not None:
        target_identity = evidence_targets.model_dump(mode="json") if isinstance(evidence_targets, EvidenceTargetSetV1) else evidence_targets
        if not isinstance(target_identity, Mapping) or not isinstance(target_identity.get("case_id"), str):
            raise ValueError("evidence targets require an explicit case_id")
        parsed_targets = parse_evidence_target_set(
            evidence_targets, run_id=run_id, case_id=target_identity["case_id"]
        )
    else:
        parsed_targets = None
    manifest, registry = _load(run_dir, evidence_targets_mode=parsed_targets is not None)

    if parsed_targets is None and (run_dir / "evidence_targets.json").is_file():
        target_state = manifest.artifacts.get("evidence_targets.json")
        target_path = run_dir / "evidence_targets.json"
        if target_state is None or target_state.status == "missing" or not target_state.content_hash:
            raise ArtifactConflictError("existing evidence_targets.json is unregistered; refusing to load")
        target_text = target_path.read_text(encoding="utf-8")
        if sha256_text(target_text) != target_state.content_hash:
            raise ArtifactConflictError("existing evidence_targets.json hash differs from its registry record")
        raw_targets = json.loads(target_text)
        parsed_targets = parse_evidence_target_set(
            raw_targets, run_id=run_id, case_id=raw_targets.get("case_id")
        )

    def search() -> None:
        questions = registry.read_json("questions.json")
        results: list[dict[str, Any]] = []
        for question_id, request in enumerate(_search_requests(questions), 1):
            response = search_provider.search(request)
            results.extend({"question_id": f"question_{question_id:03d}", **r.__dict__} for r in response.results)
        registry.write_json("search_results.json", {"schema_version": "2.0", "provider": search_provider.name, "results": results}, "search", force=force_stage == "search")

    _execute(manifest, registry, "search", search, force_stage == "search")
    if stop_after == "search": return run_dir

    documents: list[FetchedDocument] = []
    def fetch() -> None:
        previous_assets: set[str] = set()
        previous_index_path = run_dir / "source_documents" / "index.json"
        if previous_index_path.is_file():
            previous_index = read_json(previous_index_path)
            for previous_document in previous_index.get("documents", []):
                if previous_document.get("path"):
                    previous_assets.add(previous_document["path"])
                previous_assets.update(
                    asset["path"] for asset in previous_document.get("files", []) if asset.get("path")
                )
        questions = registry.read_json("questions.json")
        if hasattr(fetcher, "with_context"):
            fetcher.with_context(_fetch_context(questions))
        search_results = registry.read_json("search_results.json")["results"]
        seen: set[str] = set()
        fetch_errors: list[dict[str, str]] = []
        first_error: Exception | None = None
        for item in search_results:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            source_id = f"src_{len(documents) + 1:03d}"
            try:
                doc = fetcher.fetch(source_id, item["url"], item["title"])
            except Exception as error:
                first_error = first_error or error
                fetch_errors.append({
                    "url": sanitize_url(item["url"]),
                    "failure_code": _fetch_failure_code(error),
                    "error": safe_error_message(error),
                })
                continue
            if not doc.document_hash:
                doc = replace(doc, document_hash=sha256_text(doc.text))
            documents.append(doc)
        if not documents and first_error is not None:
            raise first_error
        for doc in documents:
            path = run_dir / "source_documents" / f"{doc.source_id}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            from fanglei.artifacts import atomic_write_text
            atomic_write_text(path, doc.text)
            if doc.raw_content is not None:
                raw_path = run_dir / "source_documents" / "raw" / f"{doc.source_id}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(raw_path, doc.raw_content)
            if doc.raw_bytes is not None:
                raw_path = run_dir / "source_documents" / "raw" / f"{doc.source_id}.pdf"
                atomic_write_bytes(raw_path, doc.raw_bytes)
            if doc.pages:
                pages_path = run_dir / "source_documents" / f"{doc.source_id}.pages.json"
                atomic_write_json(
                    pages_path,
                    {"source_id": doc.source_id, "document_hash": doc.document_hash, "pages": doc.pages},
                )
        document_rows = []
        for doc in documents:
            row = {key: value for key, value in doc.__dict__.items() if key not in {"raw_content", "raw_bytes"}}
            row.update({"path": f"source_documents/{doc.source_id}.md", "content_hash": sha256_text(doc.text)})
            files = [{"role": "normalized_text", "path": row["path"], "content_hash": row["content_hash"]}]
            if doc.raw_content is not None:
                files.append({
                    "role": "raw_response",
                    "path": f"source_documents/raw/{doc.source_id}.json",
                    "content_hash": sha256_text(doc.raw_content),
                })
            if doc.raw_bytes is not None:
                files.append({
                    "role": "raw_response",
                    "path": f"source_documents/raw/{doc.source_id}.pdf",
                    "content_hash": sha256_bytes(doc.raw_bytes),
                })
            if doc.pages:
                pages_path = run_dir / "source_documents" / f"{doc.source_id}.pages.json"
                files.append({
                    "role": "page_index",
                    "path": f"source_documents/{doc.source_id}.pages.json",
                    "content_hash": sha256_bytes(pages_path.read_bytes()),
                })
            row["files"] = files
            document_rows.append(row)
        current_assets = {
            asset["path"]
            for row in document_rows
            for asset in row.get("files", [])
            if asset.get("path")
        }
        source_root = (run_dir / "source_documents").resolve()
        for relative_path in previous_assets - current_assets:
            old_path = (run_dir / relative_path).resolve()
            if old_path.is_relative_to(source_root) and old_path.is_file():
                old_path.unlink()
        registry.write_json(
            "source_documents/index.json",
            {"schema_version": "2.1", "fetch_errors": fetch_errors, "documents": document_rows},
            "source_fetch", force=force_stage == "source_fetch",
        )

    _execute(manifest, registry, "source_fetch", fetch, force_stage == "source_fetch")
    if stop_after == "source_fetch": return run_dir
    if not documents:
        _, documents = _documents_from_index(run_dir, registry)

    def select() -> None:
        sources = _source_selection_artifact(
            run_id,
            registry,
            documents,
            source_policy=source_policy,
        )
        registry.write_json(
            "sources.json",
            sources,
            "source_selection", force=force_source_selection,
        )
    existing_sources = run_dir / "sources.json"
    force_source_selection = force_stage == "source_selection"
    if source_policy is not None:
        requested_policy = dict(source_policy)
        if existing_sources.is_file():
            existing_value = read_json(existing_sources)
            force_source_selection = force_source_selection or existing_value.get("source_policy") != requested_policy
        else:
            force_source_selection = True
    _execute(manifest, registry, "source_selection", select, force_source_selection)
    if stop_after == "source_selection": return run_dir

    target_set_sha256: str | None = None
    document_roles: dict[str, str] = {}
    if parsed_targets is not None:
        source_artifact = registry.read_json("sources.json")
        parsed_sources = parse_sources_artifact(source_artifact)
        source_policy_model = getattr(parsed_sources, "source_policy", None)
        if isinstance(source_policy_model, AuthoritativePrimarySetPolicyV1):
            if (
                source_policy_model.run_id != parsed_targets.run_id
                or source_policy_model.case_id != parsed_targets.case_id
                or source_artifact.get("package_admissibility") != "admissible"
            ):
                raise ArtifactConflictError("evidence targets do not match the approved authority source package identity")
            document_roles = {
                document.source_id: document.evidence_role
                for document in source_policy_model.approved_documents
            }
            allowed_roles = set(document_roles.values())
            if any(not set(target.source_roles).issubset(allowed_roles) for target in parsed_targets.targets):
                raise ArtifactConflictError("evidence target source_roles must match roles in the approved package")
        else:
            document_roles = {row["source_id"]: row["source_type"] for row in source_artifact["sources"]}

        target_payload = parsed_targets.model_dump(mode="json")
        target_path = run_dir / "evidence_targets.json"
        target_state = manifest.artifacts["evidence_targets.json"]
        target_force = force_stage == "evidence_targets"
        if target_path.exists():
            existing_text = target_path.read_text(encoding="utf-8")
            if target_state.status == "missing" or not target_state.content_hash:
                raise ArtifactConflictError("existing evidence_targets.json is unregistered; refusing to overwrite")
            if sha256_text(existing_text) != target_state.content_hash:
                raise ArtifactConflictError("existing evidence_targets.json hash differs from its registry record")
            existing_target = json.loads(existing_text)
            target_force = target_force or existing_target != target_payload or target_state.status != "valid"
        else:
            if target_state.status != "missing":
                raise ArtifactConflictError("registered evidence_targets.json is missing; refusing to recreate")
            target_force = True

        def save_targets() -> None:
            registry.write_json(
                "evidence_targets.json", target_payload, "evidence_targets", force=target_force
            )

        _execute(manifest, registry, "evidence_targets", save_targets, target_force)
        target_set_sha256 = manifest.artifacts["evidence_targets.json"].content_hash

    def factcheck() -> None:
        source_artifact = registry.read_json("sources.json")
        source_version = source_artifact.get("schema_version")
        parsed_source_artifact = parse_sources_artifact(source_artifact) if source_version != "2.0" else None
        sources = source_artifact["sources"]
        source_context = {row["source_id"]: row for row in sources}
        if source_artifact.get("schema_version") == "2.0" and authority_claims:
            raise ValueError("AUTHORITY_CLAIMS_REQUIRE_SOURCES_2_1: authority claims need a versioned approved source package")
        if source_artifact.get("schema_version") == "2.1" and source_artifact.get("package_admissibility") != "admissible":
            raise ValueError("SOURCE_PACKAGE_INADMISSIBLE: source package does not permit claim extraction")
        evidence = RuleBasedEvidenceExtractor().extract(
            documents,
            _question_texts(registry.read_json("questions.json")),
            evidence_targets=parsed_targets,
            document_roles=document_roles if parsed_targets is not None else None,
            target_set_sha256=target_set_sha256,
        )
        if (
            authority_claims
            and parsed_source_artifact is not None
            and isinstance(parsed_source_artifact.source_policy, AuthoritativePrimarySetPolicyV1)
        ):
            approved_statement_ids = {
                document.source_id
                for document in parsed_source_artifact.source_policy.approved_documents
                if (
                    "statement" in f"{document.document_identity} {document.evidence_role}".casefold()
                    or (
                        "meeting" in document.evidence_role.casefold()
                        and "context" in document.evidence_role.casefold()
                    )
                )
            }
            existing_evidence = {
                (item.get("source_id"), item.get("evidence_text")) for item in evidence
            }
            evidence.extend(
                item for item in extract_qualitative_primary_evidence(
                    documents,
                    approved_source_ids=approved_statement_ids,
                )
                if (item.get("source_id"), item.get("evidence_text")) not in existing_evidence
            )
        evidence = gate_evidence(evidence, documents)
        if source_artifact.get("schema_version") == "2.0":
            # Preserve the complete historical path for already materialized V2.0 runs.
            facts = verify_claims(evidence, source_context, minimum_sources_met=source_artifact["selection_status"] == "selected")
            facts["run_id"] = run_id
            facts["checked_at"] = _now()
        else:
            assert parsed_source_artifact is not None
            policy_case_id = (
                parsed_source_artifact.source_policy.case_id
                if hasattr(parsed_source_artifact.source_policy, "case_id")
                else None
            )
            resolved_authority_claims = {key: dict(value) for key, value in (authority_claims or {}).items()}
            if (
                parsed_targets is not None
                and isinstance(parsed_source_artifact.source_policy, AuthoritativePrimarySetPolicyV1)
            ):
                target_evidence = gate_evidence(
                    [item for item in evidence if item.get("evidence_target_id")], documents
                )
                generated = build_authority_claim_proposals(
                    target_evidence,
                    parsed_targets,
                    institution_display_name=parsed_source_artifact.source_policy.institution.display_name,
                )
                collision = set(resolved_authority_claims) & set(generated)
                if collision:
                    raise ArtifactConflictError("authority claim proposal key collision: " + ", ".join(sorted(collision)))
                resolved_authority_claims.update(generated)
            facts = verify_claims_v22(
                evidence,
                source_context,
                source_artifact,
                documents,
                registry.read_json("source_documents/index.json"),
                run_id=run_id,
                case_id=policy_case_id,
                authority_claims=resolved_authority_claims,
                checked_at=_now(),
            )
        registry.write_json("facts.json", facts, "factcheck", force=force_stage == "factcheck")
    _execute(manifest, registry, "factcheck", factcheck, force_stage == "factcheck")
    if stop_after == "factcheck": return run_dir

    def synthesize() -> None:
        source_artifact = registry.read_json("sources.json")
        facts = registry.read_json("facts.json")
        if "research_focus.json" in registry.graph:
            focus = ResearchFocusV1.model_validate(registry.read_json("research_focus.json"))
            research = _render_research_focus(run_id, focus, source_artifact, facts)
        else:
            questions = _question_texts(registry.read_json("questions.json"))
            research = _render_research(run_id, questions, source_artifact["sources"], facts)
        registry.write_text(
            "research.md",
            research,
            "research_synthesis",
            force=(run_dir / "research.md").exists() or force_stage == "research_synthesis",
        )
    _execute(manifest, registry, "research_synthesis", synthesize, force_stage == "research_synthesis")
    manifest.status = "analyzed"
    registry.save_manifest()
    return run_dir
