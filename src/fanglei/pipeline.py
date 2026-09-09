"""V0.2 file-artifact research pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import atomic_write_bytes, atomic_write_json, read_json, sha256_bytes, sha256_text
from fanglei.models import ArtifactState, RunManifest, StageError, StageState
from fanglei.paths import resolve_run_dir
from fanglei.providers.search import SearchProvider, SearchRequest
from fanglei.providers.document import FetchContext
from fanglei.research import FetchedDocument, RuleBasedEvidenceExtractor, deduplicate_sources, verify_claims
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
    registry.save_manifest()
    return manifest, registry


STAGE_ARTIFACT = {
    "search": "search_results.json",
    "source_fetch": "source_documents/index.json",
    "source_selection": "sources.json",
    "factcheck": "facts.json",
    "research_synthesis": "research.md",
}


def _execute(manifest: RunManifest, registry: ArtifactRegistry, stage: str, action, force: bool = False) -> None:
    previous = manifest.stages.get(stage, StageState())
    artifact_state = manifest.artifacts[STAGE_ARTIFACT[stage]]
    if previous.status == "succeeded" and artifact_state.status == "valid" and not force:
        try:
            registry.validate(STAGE_ARTIFACT[stage])
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


def run_v02_pipeline(
    run_id: str,
    runs_dir: Path,
    search_provider: SearchProvider,
    fetcher: DocumentFetcher,
    *,
    stop_after: str | None = None,
    force_stage: str | None = None,
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
                fetch_errors.append({"url": sanitize_url(item["url"]), "error": safe_error_message(error)})
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
        registry.write_json(
            "source_documents/index.json",
            {"schema_version": "2.1", "fetch_errors": fetch_errors, "documents": document_rows},
            "source_fetch", force=force_stage == "source_fetch",
        )

    _execute(manifest, registry, "source_fetch", fetch, force_stage == "source_fetch")
    if stop_after == "source_fetch": return run_dir
    if not documents:
        fields = FetchedDocument.__dataclass_fields__
        for row in registry.read_json("source_documents/index.json")["documents"]:
            values = {key: value for key, value in row.items() if key in fields}
            for asset in row.get("files", []):
                asset_path = run_dir / asset.get("path", "")
                if asset.get("role") == "raw_response" and asset_path.suffix == ".json":
                    values["raw_content"] = asset_path.read_text(encoding="utf-8")
                elif asset.get("role") == "raw_response" and asset_path.suffix == ".pdf":
                    values["raw_bytes"] = asset_path.read_bytes()
            documents.append(FetchedDocument(**values))

    def select() -> None:
        rows = deduplicate_sources(documents)
        registry.write_json(
            "sources.json",
            {"schema_version": "2.0", "selection_status": "selected" if sum(r["counts_as_independent"] for r in rows) >= 3 else "insufficient_sources", "sources": rows},
            "source_selection", force=force_stage == "source_selection",
        )
    _execute(manifest, registry, "source_selection", select, force_stage == "source_selection")
    if stop_after == "source_selection": return run_dir

    def factcheck() -> None:
        source_artifact = registry.read_json("sources.json")
        sources = source_artifact["sources"]
        source_context = {row["source_id"]: row for row in sources}
        evidence = RuleBasedEvidenceExtractor().extract(documents, _question_texts(registry.read_json("questions.json")))
        evidence = gate_evidence(evidence, documents)
        facts = verify_claims(evidence, source_context, minimum_sources_met=source_artifact["selection_status"] == "selected")
        facts["run_id"] = run_id
        facts["checked_at"] = _now()
        registry.write_json("facts.json", facts, "factcheck", force=force_stage == "factcheck")
    _execute(manifest, registry, "factcheck", factcheck, force_stage == "factcheck")
    if stop_after == "factcheck": return run_dir

    def synthesize() -> None:
        questions = _question_texts(registry.read_json("questions.json"))
        sources = registry.read_json("sources.json")["sources"]
        facts = registry.read_json("facts.json")
        registry.write_text("research.md", _render_research(run_id, questions, sources, facts), "research_synthesis", force=(run_dir / "research.md").exists() or force_stage == "research_synthesis")
    _execute(manifest, registry, "research_synthesis", synthesize, force_stage == "research_synthesis")
    manifest.status = "analyzed"
    registry.save_manifest()
    return run_dir
