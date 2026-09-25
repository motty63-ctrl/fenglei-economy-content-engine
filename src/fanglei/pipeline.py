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


class DocumentFetcher(Protocol):
    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument: ...


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load(run_dir: Path) -> tuple[RunManifest, ArtifactRegistry]:
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    registry = ArtifactRegistry(run_dir, manifest)
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
    "factcheck": "facts.json",
    "research_synthesis": "research.md",
    "angle_generation": "angles.json",
    "angle_selection": "angle.md",
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
    claims = [item.get("claim", "") for item in questions.get("claims_requiring_external_verification", [])]
    queries = [claim for claim in claims if claim] or _question_texts(questions)
    context = " ".join([questions.get("core_topic", ""), *queries])
    domain_map = {
        "bea": ("bea.gov", "BEA"),
        "world bank": ("data.worldbank.org", "World Bank"),
        "imf": ("imf.org", "IMF"),
        "oecd": ("oecd.org", "OECD"),
    }
    named_authorities = [value for marker, value in domain_map.items() if marker in context.lower()]
    requests: list[SearchRequest] = []
    for query in queries:
        core_topic = questions.get("core_topic", "").strip() or query
        target_year = next(iter(re.findall(r"(?:19|20)\d{2}", core_topic)), "")
        authority_focus = {
            "BEA": f"fourth quarter and year {target_year}",
            "World Bank": "GDP growth (annual %) United States",
            "IMF": "World Economic Outlook United States",
            "OECD": "Economic Outlook United States",
        }
        if named_authorities:
            requests.extend(
                SearchRequest(
                    query=f"{core_topic} {authority} annual real GDP growth rate {authority_focus[authority]} official data",
                    max_results=6,
                    include_domains=[domain],
                )
                for domain, authority in named_authorities
            )
        else:
            requests.append(SearchRequest(query=f"{core_topic} annual real GDP growth rate official data", max_results=12))
    return requests


def _fetch_context(questions: dict[str, Any]) -> FetchContext:
    text = " ".join([
        questions.get("core_topic", ""),
        *[item.get("claim", "") for item in questions.get("claims_requiring_external_verification", [])],
        *_question_texts(questions),
    ])
    country = "USA" if re.search(r"\bUS\b|United States|美国", text, re.I) else None
    years = tuple(sorted(set(re.findall(r"(?:19|20)\d{2}", text))))
    indicators = ("real_gdp_growth",) if re.search(r"real\s+GDP|实际GDP|实际国内生产总值", text, re.I) else ()
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


def _focus_evidence_layer(
    claim: dict[str, Any], approved_documents: dict[str, dict[str, str]]
) -> str | None:
    attestation = claim.get("authority_attestation")
    if not isinstance(attestation, dict):
        return None
    source_ids = attestation.get("source_ids", [])
    metadata = [approved_documents[source_id] for source_id in source_ids if source_id in approved_documents]
    if len(metadata) != len(source_ids) or not metadata:
        return None
    descriptors = [
        f"{row.get('document_identity', '')} {row.get('evidence_role', '')}".casefold()
        for row in metadata
    ]
    if attestation.get("kind") == "deterministic_document_comparison" and all(
        "sep" in value or "projection" in value for value in descriptors
    ):
        return "sep"
    if attestation.get("kind") == "document_report" and any(
        ("statement" in value or ("meeting" in value and "context" in value))
        and "target" in value
        for value in descriptors
    ):
        return "statement"
    return None


def _render_research_focus(
    run_id: str,
    focus: ResearchFocusV1,
    source_artifact: dict[str, Any],
    facts: dict[str, Any],
) -> str:
    """Render a focused, deterministic brief from allowed facts only."""
    sources = source_artifact.get("sources", [])
    policy = source_artifact.get("source_policy", {})
    approved_documents = {
        row["source_id"]: row
        for row in policy.get("approved_documents", [])
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    } if isinstance(policy, dict) else {}
    allowed_claims = [
        claim for claim in facts.get("claims", [])
        if isinstance(claim, dict)
        and claim.get("verification_status") == "verified"
        and claim.get("allowed_downstream") is True
    ]
    sep_claims = [claim for claim in allowed_claims if _focus_evidence_layer(claim, approved_documents) == "sep"]
    statement_claims = [
        claim for claim in allowed_claims if _focus_evidence_layer(claim, approved_documents) == "statement"
    ]

    def render_claim(claim: dict[str, Any]) -> list[str]:
        source_ids = list(dict.fromkeys(claim.get("source_ids", [])))
        lines = [f"- {claim['claim_text']} `[{claim['claim_id']}; {', '.join(source_ids)}]`"]
        for evidence in claim.get("evidence", []):
            if evidence.get("relation") != "supports" or not evidence.get("evidence_eligible", True):
                continue
            locator = evidence.get("paragraph_locator") or evidence.get("source_section") or "source excerpt"
            lines.append(f"  - Evidence ({evidence.get('source_id')}, {locator}): “{evidence.get('evidence_text', '')}”")
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
    lines.extend(["", "## A. June-to-September SEP revisions", ""])
    lines.extend(line for claim in sep_claims for line in render_claim(claim))
    if not sep_claims:
        lines.append("- No verified, downstream-allowed SEP comparison facts are available.")
    lines.extend(["", "## B. September FOMC statement context", ""])
    lines.extend(line for claim in statement_claims for line in render_claim(claim))
    if not statement_claims:
        lines.append("- No verified, downstream-allowed target-meeting statement facts are available.")
    lines.extend([
        "",
        "## Evidence boundary",
        "",
        "The SEP records FOMC participants’ projections and assessments; it is not a unified Federal Reserve commitment. "
        "The FOMC statement records the Committee’s public meeting statement. "
        "These evidence layers are presented side by side as documented context; this report does not infer a causal relationship.",
        "",
        "## Framing constraints",
        "",
    ])
    lines.extend(f"- {constraint}" for constraint in focus.constraints)
    excluded = [
        claim for claim in facts.get("claims", [])
        if not (
            isinstance(claim, dict)
            and claim.get("verification_status") == "verified"
            and claim.get("allowed_downstream") is True
            and _focus_evidence_layer(claim, approved_documents) in {"sep", "statement"}
        )
    ]
    lines.extend(["", "## Excluded fact records", ""])
    lines.append(
        f"{len(excluded)} records were not used as substantive assertions because they are unverified, "
        "not allowed downstream, or outside the two focused evidence layers."
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
) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

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
        evidence = RuleBasedEvidenceExtractor().extract(documents, _question_texts(registry.read_json("questions.json")))
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
            facts = verify_claims_v22(
                evidence,
                source_context,
                source_artifact,
                documents,
                registry.read_json("source_documents/index.json"),
                run_id=run_id,
                case_id=policy_case_id,
                authority_claims={key: dict(value) for key, value in (authority_claims or {}).items()},
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
