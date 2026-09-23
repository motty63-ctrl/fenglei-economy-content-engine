"""Import manually approved research checkpoints into formal run artifacts.

This path is deliberately separate from native research generation. It performs
only deterministic structure conversion and provenance completion against the
checkpoint's explicit official URL allowlist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import json
import os
import re
import shutil
import ssl

from fanglei.artifact_registry import ArtifactRegistry, IMPORTED_ARTIFACT_GRAPH
from fanglei.artifacts import atomic_write_bytes, atomic_write_json, atomic_write_text, sha256_bytes, sha256_text
from fanglei.checkpoint_contract import (
    classify_checkpoint_version,
    parse_approved_checkpoint_v2,
)
from fanglei.content_models import AngleCandidate
from fanglei.models import RunManifest, StageState
from fanglei.paths import next_run_id


class SourceFetchError(RuntimeError):
    """An allowlisted provenance URL could not be fetched safely."""


class SourceContentChangedError(RuntimeError):
    """An immutable pinned source URL returned different content."""


class CheckpointV2ImportNotImplementedError(RuntimeError):
    """V2 contract preflight exists, but V2 materialization is a later phase."""


@dataclass(frozen=True)
class SourceCapture:
    url: str
    content: bytes
    content_type: str
    title: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None

    @property
    def content_sha256(self) -> str:
        return sha256_bytes(self.content)


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> SourceCapture: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class OfficialUrlFetcher:
    """Small strict fetcher: HTTPS only, no redirects, one exact URL per call."""

    def fetch(self, url: str) -> SourceCapture:
        if not url.startswith("https://"):
            raise SourceFetchError("Only HTTPS provenance sources are allowed")
        request = Request(url, headers={"User-Agent": "Fanglei-Checkpoint-Importer/1.0"})
        opener = build_opener(_NoRedirect(), ssl.create_default_context())
        try:
            with opener.open(request, timeout=30) as response:
                if response.geturl() != url:
                    raise SourceFetchError("Redirected source URL is outside the exact allowlist")
                content = response.read(25_000_001)
                if len(content) > 25_000_000:
                    raise SourceFetchError("Source exceeds the 25 MB provenance capture limit")
                content_type = response.headers.get("Content-Type", "application/octet-stream")
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise SourceFetchError(f"Could not capture allowlisted source: {error}") from error
        title, published_at = _extract_capture_metadata(content, content_type)
        return SourceCapture(url=url, content=content, content_type=content_type,
                             title=title, published_at=published_at, retrieved_at=_now())


class _VisibleText(HTMLParser):
    BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section"}
    HIDDEN = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN:
            self.hidden += 1
        if not self.hidden and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HIDDEN and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


class _HtmlMetadata(HTMLParser):
    DATE_KEYS = {"article:published_time", "datepublished", "pubdate", "dc.date", "dcterms.issued"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.published_at: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            published = values.get("content", "").strip()
            if key in self.DATE_KEYS and published:
                self.published_at = published
        if tag.lower() == "time" and values.get("datetime") and self.published_at is None:
            self.published_at = values["datetime"]

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


_RUNTIME_KEYS = {
    "imported_at", "created_at", "updated_at", "executed_at", "started_at",
    "finished_at", "generated_at", "processed_at", "checked_at", "fetched_at",
    "retrieved_at", "runtime_metadata",
}


def _without_runtime(value: Any, *, normalize_run_id: bool = False) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key.lower() in _RUNTIME_KEYS:
                continue
            if normalize_run_id and key == "run_id":
                result[key] = "<run-id>"
            else:
                result[key] = _without_runtime(child, normalize_run_id=normalize_run_id)
        return result
    if isinstance(value, list):
        return [_without_runtime(item, normalize_run_id=normalize_run_id) for item in value]
    return value


def _digest_json(value: Any) -> str:
    return sha256_text(_canonical_json(value))


def _text_from_capture(capture: SourceCapture) -> str:
    content_type = capture.content_type.lower()
    if "pdf" in content_type or capture.content.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(capture.content))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as error:
            raise SourceFetchError(f"Could not extract text from captured PDF: {error}") from error
    text = capture.content.decode("utf-8", errors="replace")
    if "html" in content_type or re.search(r"<html\b|<!doctype html", text, re.I):
        parser = _VisibleText()
        parser.feed(text)
        text = "".join(parser.parts)
    return re.sub(r"[ \t\xa0]+", " ", text).replace("\r\n", "\n").replace("\r", "\n")


def _extract_capture_metadata(content: bytes, content_type: str) -> tuple[str | None, str | None]:
    if "html" in content_type.lower() or re.search(rb"<html\b|<!doctype html", content[:4096], re.I):
        parser = _HtmlMetadata()
        parser.feed(content.decode("utf-8", errors="replace"))
        title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip() or None
        return title, parser.published_at
    if "pdf" in content_type.lower() or content.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
            import io

            metadata = PdfReader(io.BytesIO(content)).metadata
            return ((str(metadata.title).strip() if metadata and metadata.title else None),
                    (metadata.creation_date.date().isoformat() if metadata and metadata.creation_date else None))
        except Exception:
            return None, None
    return None, None


def _source_cache_key(url: str) -> str:
    return sha256_text(url)


def _read_capture(cache_dir: Path, url: str) -> SourceCapture | None:
    index = cache_dir / _source_cache_key(url) / "pinned.json"
    if not index.is_file():
        return None
    metadata = json.loads(index.read_text("utf-8"))
    content_path = index.parent / metadata["content_file"]
    if not content_path.is_file():
        raise SourceFetchError(f"Pinned source capture is incomplete for {url}")
    content = content_path.read_bytes()
    actual = sha256_bytes(content)
    if actual != metadata.get("content_sha256"):
        raise SourceFetchError(f"Pinned source capture hash mismatch for {url}")
    return SourceCapture(
        url=url, content=content, content_type=metadata["content_type"],
        title=metadata.get("title"), published_at=metadata.get("published_at"),
        retrieved_at=metadata.get("retrieved_at"),
    )


def _pin_capture(cache_dir: Path, capture: SourceCapture) -> SourceCapture:
    root = cache_dir / _source_cache_key(capture.url)
    root.mkdir(parents=True, exist_ok=True)
    current = _read_capture(cache_dir, capture.url)
    if current is not None:
        if current.content_sha256 != capture.content_sha256:
            raise SourceContentChangedError(
                f"SOURCE_CONTENT_CHANGED: {capture.url} pinned={current.content_sha256} observed={capture.content_sha256}"
            )
        return current
    content_file = f"{capture.content_sha256}.bin"
    content_path = root / content_file
    if not content_path.exists():
        with content_path.open("xb") as handle:
            handle.write(capture.content)
            handle.flush()
            os.fsync(handle.fileno())
    atomic_write_json(root / "pinned.json", {
        "url": capture.url,
        "content_sha256": capture.content_sha256,
        "content_file": content_file,
        "content_type": capture.content_type,
        "title": capture.title,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at or _now(),
    })
    return _read_capture(cache_dir, capture.url) or capture


def _source_text_and_excerpt(capture: SourceCapture, anchor: str) -> tuple[str, str, str | None]:
    source_text = _text_from_capture(capture)
    if not isinstance(anchor, str) or not anchor.strip():
        raise ValueError("PROVENANCE_EXCERPT_MISSING")
    positions = [match.start() for match in re.finditer(re.escape(anchor), source_text)]
    if len(positions) != 1:
        code = "PROVENANCE_EXCERPT_NOT_FOUND" if not positions else "PROVENANCE_EXCERPT_AMBIGUOUS"
        raise ValueError(code)
    position = positions[0]
    line = source_text.count("\n", 0, position) + 1
    return source_text, anchor, f"line {line}"


def _validate_json_schema(value: Any, schema_path: Path) -> list[dict[str, str]]:
    try:
        import jsonschema
    except ImportError:
        return [{"code": "SCHEMA_VALIDATOR_MISSING", "message": "jsonschema is required for formal schema validation"}]
    schema = json.loads(schema_path.read_text("utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        {"code": "SCHEMA_INVALID", "message": f"{'/'.join(str(x) for x in error.absolute_path)}: {error.message}"}
        for error in sorted(validator.iter_errors(value), key=lambda item: list(map(str, item.absolute_path)))
    ]


@dataclass
class ImportResult:
    staging_dir: Path
    checkpoint_fingerprint: str
    mapping_sha256: str
    semantic_artifact_hashes: dict[str, str]
    gates: dict[str, Any]
    status: str
    artifact_graph: dict[str, tuple[str, tuple[str, ...]]]
    run_dir: Path | None = None


class ApprovedCheckpointMaterializer:
    """Pure content conversion from a checkpoint dictionary to formal artifacts."""

    def __init__(self, project_root: Path, importer_version: str) -> None:
        self.project_root = Path(project_root)
        self.importer_version = importer_version

    def materialize(self, checkpoint: dict[str, Any], staging_dir: Path, captures: dict[str, SourceCapture],
                    checkpoint_content_sha256: str, checkpoint_fingerprint: str) -> ImportResult:
        staging_dir = Path(staging_dir)
        materialized = staging_dir / "materialized"
        if materialized.exists():
            shutil.rmtree(materialized)
        materialized.mkdir(parents=True)
        issues: list[dict[str, str]] = []
        cp = _without_runtime(checkpoint)
        source_rows = cp.get("sources", [])
        claim_rows = cp.get("claims", [])
        evidence_rows = cp.get("evidence", [])
        script_in = cp.get("script", {})
        angle_in = cp.get("angle", {})
        sentence_rows = script_in.get("sentences", []) if isinstance(script_in, dict) else []

        mappings = {
            "sources": _make_mapping(source_rows, "source", issues),
            "claims": _make_mapping(claim_rows, "claim", issues),
            "evidence": _make_mapping(evidence_rows, "evidence", issues),
            "angles": _make_mapping([angle_in] if angle_in else [], "angle", issues),
            "scripts": _make_mapping([script_in] if script_in else [], "script", issues),
            "sentences": _make_mapping(sentence_rows, "sentence", issues),
        }
        id_lookup = {kind: {item["source_id"]: item["canonical_id"] for item in rows}
                     for kind, rows in mappings.items()}
        binding_rows: list[dict[str, Any]] = []
        all_refs_valid = True
        for sentence in sentence_rows:
            external_sentence = sentence.get("external_id")
            claim_ids = sentence.get("claim_ids", [])
            evidence_ids = sentence.get("evidence_ids", [])
            missing = [claim for claim in claim_ids if claim not in id_lookup["claims"]]
            missing.extend(evidence for evidence in evidence_ids if evidence not in id_lookup["evidence"])
            if missing:
                all_refs_valid = False
                for unknown in missing:
                    issues.append({"code": "UNKNOWN_CLAIM_ID" if unknown in claim_ids else "UNKNOWN_EVIDENCE_ID",
                                   "message": f"Sentence {external_sentence} references unknown ID {unknown}"})
            binding_rows.append({
                "sentence_source_id": external_sentence,
                "sentence_id": id_lookup["sentences"].get(external_sentence),
                "claim_ids": [id_lookup["claims"][item] for item in claim_ids if item in id_lookup["claims"]],
                "evidence_ids": [id_lookup["evidence"][item] for item in evidence_ids if item in id_lookup["evidence"]],
            })
        mapping = {
            "schema_version": "1.0",
            "checkpoint_fingerprint": checkpoint_fingerprint,
            "checkpoint_content_sha256": checkpoint_content_sha256,
            "checkpoint_schema_version": cp.get("checkpoint_schema_version"),
            "importer_version": self.importer_version,
            "mappings": mappings,
            "bindings": binding_rows,
        }
        mapping_sha256 = _digest_json(mapping)

        resolved_sources: dict[str, dict[str, Any]] = {}
        normalized_documents: list[dict[str, Any]] = []
        capture_rows: dict[str, dict[str, Any]] = {}
        for source in source_rows:
            external_id, url = source.get("external_id"), source.get("url")
            if url not in captures:
                issues.append({"code": "SOURCE_NOT_CAPTURED", "message": f"No pinned capture for {url}"})
                continue
            capture = captures[url]
            source_id = id_lookup["sources"].get(external_id)
            resolved_sources[external_id] = {
                "source_id": source_id, "source_external_id": external_id,
                "title": source.get("title") or capture.title,
                "original_url": url, "official": source.get("official") is True,
                "content_type": capture.content_type,
                "content_sha256": capture.content_sha256,
                "published_at": source.get("published_at") or capture.published_at,
                "retrieved_at": capture.retrieved_at or _now(),
            }
            try:
                source_text = _text_from_capture(capture)
            except SourceFetchError as error:
                issues.append({"code": "PROVENANCE_TEXT_EXTRACTION_FAILED", "message": str(error)})
                continue
            document_path = f"source_documents/{source_id}.txt"
            atomic_write_text(materialized / document_path, source_text)
            raw_path = f"source_documents/{source_id}.bin"
            atomic_write_bytes(materialized / raw_path, capture.content)
            normalized_documents.append({
                "source_id": source_id,
                "path": document_path,
                "content_hash": sha256_text(source_text),
                "original_url": url,
                "files": [{"path": raw_path, "content_hash": capture.content_sha256}],
            })
            capture_rows[url] = {"content_sha256": capture.content_sha256, "content_type": capture.content_type}

        completed_evidence: dict[str, dict[str, Any]] = {}
        provenance_ok = not any(issue["code"].startswith("SOURCE_") or issue["code"].startswith("PROVENANCE_")
                                for issue in issues)
        for evidence in evidence_rows:
            external_evidence_id = evidence.get("external_id")
            source_ids = evidence.get("source_ids", [])
            if len(source_ids) != 1 or source_ids[0] not in resolved_sources:
                provenance_ok = False
                issues.append({"code": "PROVENANCE_SOURCE_REFERENCE_INVALID",
                               "message": f"Evidence {external_evidence_id} must reference one resolved checkpoint source"})
                continue
            source_external = source_ids[0]
            capture = captures.get(resolved_sources[source_external]["original_url"])
            if capture is None:
                provenance_ok = False
                continue
            try:
                _, excerpt, locator = _source_text_and_excerpt(capture, evidence.get("excerpt_anchor"))
            except ValueError as error:
                provenance_ok = False
                issues.append({"code": str(error), "message": f"Evidence {external_evidence_id} excerpt cannot be recovered"})
                continue
            completed_evidence[external_evidence_id] = {
                "evidence_id": id_lookup["evidence"].get(external_evidence_id),
                "evidence_external_id": external_evidence_id,
                "source_id": resolved_sources[source_external]["source_id"],
                "source_external_id": source_external,
                "evidence_text": excerpt,
                "source_section": evidence.get("source_section"),
                "paragraph_locator": evidence.get("paragraph_locator") or locator,
                "published_at": evidence.get("published_at") or resolved_sources[source_external]["published_at"],
                "retrieved_at": evidence.get("retrieved_at") or resolved_sources[source_external]["retrieved_at"],
                "original_url": resolved_sources[source_external]["original_url"],
                "relation": evidence.get("relation"),
                "evidence_rationale": evidence.get("evidence_rationale"),
                "excerpt_anchor": evidence.get("excerpt_anchor"),
            }

        # Resolve every claim without deriving facts from identifiers.
        facts_claims: list[dict[str, Any]] = []
        for claim in claim_rows:
            external_id = claim.get("external_id")
            claim_evidence_ids = claim.get("evidence_ids", [])
            evidence_items = [completed_evidence[item] for item in claim_evidence_ids if item in completed_evidence]
            source_external_ids = claim.get("source_ids", [])
            if any(source_id not in resolved_sources for source_id in source_external_ids):
                provenance_ok = False
                issues.append({"code": "PROVENANCE_SOURCE_REFERENCE_INVALID",
                               "message": f"Claim {external_id} references unresolved checkpoint source"})
            if not evidence_items:
                provenance_ok = False
                issues.append({"code": "CLAIM_EVIDENCE_MISSING", "message": f"Claim {external_id} has no completed evidence"})
            facts_claims.append({
                "claim_id": id_lookup["claims"].get(external_id),
                "claim_external_id": external_id,
                "claim_text": claim.get("proposition"),
                "claim_type": claim.get("classification"),
                "verification_status": claim.get("verification_status"),
                "source_ids": [resolved_sources[item]["source_id"] for item in source_external_ids if item in resolved_sources],
                "evidence": [{key: item.get(key) for key in (
                    "source_id", "evidence_text", "source_section", "paragraph_locator", "published_at",
                    "retrieved_at", "original_url", "relation",
                )} for item in evidence_items],
                "verification_reason": claim.get("rationale") or claim.get("verification_reason"),
                "allowed_downstream": claim.get("allowed_downstream"),
            })

        required_claim_fields = ("claim_text", "claim_type", "verification_status", "verification_reason", "allowed_downstream")
        for claim in facts_claims:
            for key in required_claim_fields:
                if claim.get(key) is None or claim.get(key) == "":
                    issues.append({"code": "CLAIM_FIELD_MISSING", "message": f"Claim {claim.get('claim_external_id')} missing {key}"})
        facts = {
            "schema_version": "2.0",
            "run_id": "checkpoint-import-staging",
            "checked_at": _now(),
            "policy_version": "approved-checkpoint-import/1.0",
            "summary": {"source": "approved_checkpoint", "claim_count": len(facts_claims)},
            "claims": facts_claims,
        }

        angle_id = id_lookup["angles"].get(angle_in.get("external_id")) if isinstance(angle_in, dict) else None
        angle_payload: dict[str, Any] = {}
        try:
            angle_data = {key: value for key, value in angle_in.items() if key != "external_id"}
            angle_data["angle_id"] = angle_id
            angle_data["supporting_claim_ids"] = [id_lookup["claims"][item]
                                                 for item in angle_in.get("supporting_claim_ids", [])
                                                 if item in id_lookup["claims"]]
            for unknown in set(angle_in.get("supporting_claim_ids", [])) - set(id_lookup["claims"]):
                all_refs_valid = False
                issues.append({"code": "UNKNOWN_CLAIM_ID", "message": f"Angle references unknown claim {unknown}"})
            angle = AngleCandidate.model_validate(angle_data)
            angle_payload = angle.model_dump(mode="json")
        except Exception as error:
            issues.append({"code": "ANGLE_INVALID", "message": str(error)})

        script_payload: dict[str, Any] = {}
        sentence_texts: list[str] = []
        original_script = script_in.get("text") if isinstance(script_in, dict) else None
        script_bytes = original_script.encode("utf-8") if isinstance(original_script, str) else b""
        if not isinstance(original_script, str):
            issues.append({"code": "SCRIPT_TEXT_MISSING", "message": "Approved script text is required"})
        for sentence in sentence_rows:
            start, end = sentence.get("byte_start"), sentence.get("byte_end")
            try:
                if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
                    raise ValueError("invalid byte offsets")
                text = script_bytes[start:end].decode("utf-8")
                if not text or text != sentence.get("text", text):
                    raise ValueError("sentence text and UTF-8 byte offsets disagree")
                sentence_texts.append(text)
            except (ValueError, UnicodeDecodeError) as error:
                issues.append({"code": "SCRIPT_SENTENCE_OFFSETS_INVALID",
                               "message": f"Sentence {sentence.get('external_id')}: {error}"})
                sentence_texts.append("")
        if original_script is not None and sentence_texts:
            # Whitespace between independently identified sentences is allowed; all
            # non-whitespace source text must be represented exactly once.
            covered = bytearray(len(script_bytes))
            for sentence in sentence_rows:
                start, end = sentence.get("byte_start"), sentence.get("byte_end")
                if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(covered):
                    covered[start:end] = b"\x01" * (end - start)
            if any(byte not in b" \t\r\n" for byte, marker in zip(script_bytes, covered) if marker == 0):
                issues.append({"code": "SCRIPT_SENTENCE_COVERAGE_INCOMPLETE",
                               "message": "Sentence byte ranges do not cover all approved script text"})
        script_sentences: list[dict[str, Any]] = []
        for sentence, text in zip(sentence_rows, sentence_texts):
            external_claims = sentence.get("claim_ids", [])
            # The formal V0.3 schema permits claim references only for verified facts.
            emitted_claims = external_claims if sentence.get("sentence_type") == "verified_fact" else []
            canonical_claims = [id_lookup["claims"][item] for item in emitted_claims if item in id_lookup["claims"]]
            script_sentences.append({
                "sentence_id": id_lookup["sentences"].get(sentence.get("external_id")),
                "section": sentence.get("section"),
                "sentence_type": sentence.get("sentence_type"),
                "text": text,
                "claim_ids": canonical_claims,
            })
        if angle_id and isinstance(script_in, dict):
            script_payload = {
                "schema_version": "3.0",
                "script_id": id_lookup["scripts"].get(script_in.get("external_id")),
                "angle_id": angle_id,
                "title": script_in.get("title"),
                "target_duration_seconds": script_in.get("target_duration_seconds"),
                "speaking_rate_chars_per_second": script_in.get("speaking_rate_chars_per_second"),
                "spoken_character_count": script_in.get("spoken_character_count"),
                "estimated_duration_seconds": script_in.get("estimated_duration_seconds"),
                "sentences": script_sentences,
            }

        if not all_refs_valid:
            schema_issues = [item for item in issues if item["code"].startswith("UNKNOWN_")]
        else:
            schema_issues = []
        schema_root = Path(__file__).resolve().parents[2]
        if facts_claims:
            schema_issues.extend(_validate_json_schema(facts, schema_root / "docs/v0.2/facts.schema.json"))
        else:
            schema_issues.append({"code": "CLAIMS_MISSING", "message": "At least one formal claim is required"})
        if script_payload:
            schema_issues.extend(_validate_json_schema(script_payload, schema_root / "docs/v0.3/script-contract.schema.json"))
        else:
            schema_issues.append({"code": "SCRIPT_INVALID", "message": "Script could not be materialized"})
        if not all_refs_valid:
            schema_issues.extend(item for item in issues if item["code"].startswith("UNKNOWN_"))
        schema_failure_codes = {
            "ANGLE_INVALID", "SCRIPT_TEXT_MISSING", "SCRIPT_SENTENCE_OFFSETS_INVALID",
            "SCRIPT_SENTENCE_COVERAGE_INCOMPLETE", "CLAIM_FIELD_MISSING", "CLAIMS_MISSING",
            "SOURCE_ID_MISSING", "SOURCE_ID_DUPLICATE", "RESEARCH_TEXT_MISSING",
        }
        schema_issues.extend(item for item in issues if item["code"] in schema_failure_codes)

        script_binding_total = sum(len(item.get("claim_ids", [])) + len(item.get("evidence_ids", [])) for item in sentence_rows)
        script_binding_good = sum(len(item["claim_ids"]) + len(item["evidence_ids"]) for item in binding_rows)
        script_coverage = 1.0 if script_binding_total == 0 else script_binding_good / script_binding_total
        fact_binding_total = sum(len(item.get("evidence_ids", [])) for item in claim_rows)
        fact_binding_good = sum(len(item.get("evidence", [])) for item in facts_claims)
        fact_coverage = 1.0 if fact_binding_total == 0 else fact_binding_good / fact_binding_total
        schema_passed = not schema_issues
        gates = {
            "schema": {"passed": schema_passed},
            "provenance": {"passed": provenance_ok},
            "fact_coverage": {"passed": fact_coverage == 1.0, "coverage": round(fact_coverage, 6)},
            "script_coverage": {"passed": script_coverage == 1.0, "coverage": round(script_coverage, 6)},
            "issues": _dedupe_issues(schema_issues + issues),
        }
        passed = all(gates[key]["passed"] for key in ("schema", "provenance", "fact_coverage", "script_coverage"))

        if provenance_ok and all_refs_valid:
            # Only write facts after all referenced source excerpts have been recovered.
            _write_json(materialized / "approved_checkpoint.json", cp)
            _write_json(materialized / "id_mapping.json", mapping)
            _write_json(materialized / "source_documents/index.json", {"documents": normalized_documents})
            _write_json(materialized / "sources.json", {"schema_version": "1.0", "sources": list(resolved_sources.values())})
            _write_json(materialized / "facts.json", facts)
            research_text = cp.get("research", {}).get("content") if isinstance(cp.get("research"), dict) else None
            if not isinstance(research_text, str):
                issues.append({"code": "RESEARCH_TEXT_MISSING", "message": "Approved research content is required"})
                gates["schema"]["passed"] = False
                gates["issues"] = _dedupe_issues(gates["issues"] + issues[-1:])
                passed = False
            else:
                atomic_write_text(materialized / "research.md", research_text)
            if angle_payload:
                _write_json(materialized / "angles.json", {"schema_version": "1.0", "selected_angle_id": angle_id,
                                                           "candidates": [angle_payload]})
                _write_text(materialized / "angle.md", _angle_markdown(angle_payload))
            if script_payload:
                _write_json(materialized / "script.json", script_payload)
                _write_text(materialized / "script.md", original_script)
            import_manifest = {
                "schema_version": "1.0",
                "checkpoint_id": cp.get("checkpoint_id"),
                "checkpoint_content_sha256": checkpoint_content_sha256,
                "checkpoint_fingerprint": checkpoint_fingerprint,
                "checkpoint_schema_version": cp.get("checkpoint_schema_version"),
                "importer_version": self.importer_version,
                "original_ids": {kind: [row["source_id"] for row in rows] for kind, rows in mappings.items()},
                "canonical_ids": {kind: [row["canonical_id"] for row in rows] for kind, rows in mappings.items()},
                "id_mapping_sha256": mapping_sha256,
                "pinned_sources": capture_rows,
                "semantic_artifact_hashes": _semantic_hashes(materialized),
                "gates": gates,
                "imported_at": _now(),
            }
            _write_json(materialized / "import_manifest.json", import_manifest)
            candidate_run = {
                "schema_version": "2.0",
                "run_id": f"checkpoint-import-{checkpoint_fingerprint[:16]}",
                "created_at": _now(), "updated_at": _now(), "status": "created",
                "stages": {"checkpoint_import": {"status": "succeeded", "attempts": 1}},
                "artifacts": {},
            }
            _write_json(materialized / "candidate-run.json", candidate_run)
        _write_json(staging_dir / "gates.json", gates)
        semantic_hashes = _semantic_hashes(materialized)
        return ImportResult(
            staging_dir=staging_dir, checkpoint_fingerprint=checkpoint_fingerprint,
            mapping_sha256=mapping_sha256, semantic_artifact_hashes=semantic_hashes,
            gates=gates, status="passed" if passed else "failed",
            artifact_graph=IMPORTED_ARTIFACT_GRAPH.copy(),
        )


class CheckpointImporter:
    def __init__(self, runs_dir: Path, source_cache_dir: Path, source_fetcher: SourceFetcher | None = None,
                 importer_version: str = "1.0") -> None:
        self.runs_dir = Path(runs_dir).resolve()
        self.project_root = self.runs_dir.parent
        self.source_cache_dir = Path(source_cache_dir).resolve()
        self.staging_root = self.project_root / ".checkpoint-staging"
        self.source_fetcher = source_fetcher or OfficialUrlFetcher()
        self.importer_version = importer_version
        self.materializer = ApprovedCheckpointMaterializer(self.project_root, importer_version)
        self._last_allowlist: set[str] = set()

    def stage(self, checkpoint: dict[str, Any]) -> ImportResult:
        if isinstance(checkpoint, dict):
            version = classify_checkpoint_version(checkpoint)
            if version == "v2":
                parse_approved_checkpoint_v2(checkpoint)
                raise CheckpointV2ImportNotImplementedError(
                    "V2 checkpoint contract passed preflight; importer materialization is not implemented in Phase 1"
                )
        issues = _validate_checkpoint_envelope(checkpoint)
        semantic_checkpoint = _without_runtime(checkpoint)
        content_sha = _digest_json(semantic_checkpoint)
        checkpoint_version = checkpoint.get("checkpoint_schema_version") if isinstance(checkpoint, dict) else None
        fingerprint = _digest_json({
            "checkpoint_content_sha256": content_sha,
            "checkpoint_schema_version": checkpoint_version,
            "importer_version": self.importer_version,
        })
        # Keep the leaf short enough for Windows MAX_PATH while the full digest
        # remains pinned in the package manifest and verified on reuse.
        staging = self.staging_root / f"cp-{fingerprint[:20]}"
        staging.mkdir(parents=True, exist_ok=True)
        fingerprint_path = staging / "checkpoint_fingerprint.json"
        if fingerprint_path.is_file():
            previous = json.loads(fingerprint_path.read_text("utf-8"))
            if previous.get("checkpoint_fingerprint") != fingerprint:
                raise RuntimeError("Staging fingerprint prefix collision; refusing to reuse package")
        atomic_write_json(staging / "checkpoint_fingerprint.json", {
            "checkpoint_content_sha256": content_sha,
            "checkpoint_schema_version": checkpoint_version,
            "importer_version": self.importer_version,
            "checkpoint_fingerprint": fingerprint,
            "imported_at": _now(),
        })
        if issues:
            gates = {"schema": {"passed": False}, "provenance": {"passed": False},
                     "fact_coverage": {"passed": False, "coverage": 0.0},
                     "script_coverage": {"passed": False, "coverage": 0.0}, "issues": issues}
            atomic_write_json(staging / "gates.json", gates)
            return ImportResult(staging, fingerprint, "", {}, gates, "failed", IMPORTED_ARTIFACT_GRAPH.copy())
        allowlist = {row["url"] for row in checkpoint["sources"]}
        self._last_allowlist = allowlist
        captures: dict[str, SourceCapture] = {}
        provenance_issues: list[dict[str, str]] = []
        for source in checkpoint["sources"]:
            url = source["url"]
            try:
                capture = _read_capture(self.source_cache_dir, url)
                if capture is None:
                    fetched = self.source_fetcher.fetch(url)
                    if fetched.url != url:
                        raise SourceFetchError("Fetcher returned a URL different from the allowlisted URL")
                    capture = _pin_capture(self.source_cache_dir, fetched)
                captures[url] = capture
            except SourceContentChangedError as error:
                provenance_issues.append({"code": "SOURCE_CONTENT_CHANGED", "message": str(error)})
            except Exception as error:
                provenance_issues.append({"code": "SOURCE_CAPTURE_FAILED", "message": str(error)})
        result = self.materializer.materialize(checkpoint, staging, captures, content_sha, fingerprint)
        if provenance_issues:
            result.gates["provenance"]["passed"] = False
            result.gates["issues"] = _dedupe_issues(result.gates["issues"] + provenance_issues)
            result.status = "failed"
            atomic_write_json(staging / "gates.json", result.gates)
            result.semantic_artifact_hashes = _semantic_hashes(staging / "materialized")
        return result

    def refresh_source(self, url: str, fetcher: SourceFetcher | None = None) -> SourceCapture:
        if url not in self._last_allowlist:
            raise SourceFetchError("URL is not in the approved checkpoint source allowlist")
        old = _read_capture(self.source_cache_dir, url)
        if old is None:
            raise SourceFetchError("No pinned capture exists for this checkpoint URL")
        new = (fetcher or self.source_fetcher).fetch(url)
        if new.url != url or new.content_sha256 != old.content_sha256:
            raise SourceContentChangedError(
                f"SOURCE_CONTENT_CHANGED: {url} pinned={old.content_sha256} observed={new.content_sha256}"
            )
        return old

    def import_checkpoint(self, checkpoint: dict[str, Any], *, run_title: str = "approved-checkpoint") -> ImportResult:
        result = self.stage(checkpoint)
        if result.status != "passed":
            return result
        existing = self._find_imported_run(result.checkpoint_fingerprint)
        if existing is not None:
            result.run_dir = existing
            result.status = "promoted"
            return result
        result.run_dir = self._promote(result, run_title)
        result.status = "promoted"
        return result

    def _find_imported_run(self, fingerprint: str) -> Path | None:
        if not self.runs_dir.is_dir():
            return None
        for run_dir in self.runs_dir.iterdir():
            manifest_path = run_dir / "import_manifest.json"
            if run_dir.is_dir() and manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    if manifest.get("checkpoint_fingerprint") == fingerprint:
                        return run_dir
                except (OSError, json.JSONDecodeError):
                    continue
        return None

    def _promote(self, result: ImportResult, run_title: str) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_id = next_run_id(self.runs_dir, run_title)
        destination = self.runs_dir / run_id
        temporary = self.runs_dir / f".{run_id}.importing"
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(result.staging_dir / "materialized", temporary)
        try:
            (temporary / "candidate-run.json").replace(temporary / "run.json")
            now = _now()
            stages = {"checkpoint_import": StageState(status="succeeded", attempts=1, finished_at=now)}
            manifest = RunManifest(run_id=run_id, created_at=now, updated_at=now,
                                   status="created", stages=stages)
            # Preserve imported marker and populate actual graph hashes in dependency order.
            facts_path = temporary / "facts.json"
            facts = json.loads(facts_path.read_text("utf-8"))
            facts["run_id"] = run_id
            atomic_write_json(facts_path, facts)
            registry = ArtifactRegistry(temporary, manifest)
            _registry_write_json(registry, "approved_checkpoint.json", "checkpoint_import")
            _registry_write_json(registry, "id_mapping.json", "checkpoint_materialize")
            _registry_write_json(registry, "import_manifest.json", "checkpoint_materialize")
            _registry_write_json(registry, "source_documents/index.json", "checkpoint_provenance")
            _registry_write_json(registry, "sources.json", "checkpoint_provenance")
            _registry_write_json(registry, "facts.json", "checkpoint_materialize")
            _registry_write_text(registry, "research.md", "checkpoint_materialize")
            _registry_write_json(registry, "angles.json", "checkpoint_materialize")
            _registry_write_text(registry, "angle.md", "checkpoint_materialize")
            _registry_write_json(registry, "script.json", "checkpoint_materialize")
            _registry_write_text(registry, "script.md", "checkpoint_materialize")
            registry.save_manifest()
            # A run is visible only after the full tree and manifest are complete.
            if destination.exists():
                raise FileExistsError(destination)
            os.replace(temporary, destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return destination


def _make_mapping(rows: list[dict[str, Any]], kind: str, issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        external_id = row.get("external_id") if isinstance(row, dict) else None
        if not isinstance(external_id, str) or not external_id:
            issues.append({"code": "SOURCE_ID_MISSING", "message": f"{kind} row {index} has no external_id"})
            continue
        if external_id in seen:
            issues.append({"code": "SOURCE_ID_DUPLICATE", "message": f"Duplicate {kind} external_id {external_id}"})
            continue
        seen.add(external_id)
        result.append({"source_id": external_id, "canonical_id": f"{kind}_{index:03d}", "source_order": index})
    return result


def _validate_checkpoint_envelope(checkpoint: Any) -> list[dict[str, str]]:
    if not isinstance(checkpoint, dict):
        return [{"code": "CHECKPOINT_NOT_OBJECT", "message": "Checkpoint must be a JSON object"}]
    issues = []
    for field in ("checkpoint_schema_version", "checkpoint_id", "approval", "research", "sources", "claims", "evidence", "angle", "script"):
        if field not in checkpoint:
            issues.append({"code": "CHECKPOINT_FIELD_MISSING", "message": f"Missing required checkpoint field: {field}"})
    if not isinstance(checkpoint.get("approval"), dict) or checkpoint["approval"].get("status") != "approved":
        issues.append({"code": "CHECKPOINT_NOT_APPROVED", "message": "Checkpoint approval.status must be approved"})
    if not isinstance(checkpoint.get("sources"), list) or not checkpoint.get("sources"):
        issues.append({"code": "CHECKPOINT_SOURCES_MISSING", "message": "Checkpoint must explicitly list source URLs"})
    else:
        for source in checkpoint["sources"]:
            if not isinstance(source, dict) or source.get("official") is not True or not str(source.get("url", "")).startswith("https://"):
                issues.append({"code": "SOURCE_NOT_ALLOWLISTABLE", "message": "Every checkpoint source must be explicitly official and HTTPS"})
    for name in ("claims", "evidence"):
        rows = checkpoint.get(name)
        if not isinstance(rows, list) or not rows:
            issues.append({"code": f"CHECKPOINT_{name.upper()}_MISSING", "message": f"Checkpoint must contain {name}"})
        elif any(not isinstance(row, dict) for row in rows):
            issues.append({"code": f"CHECKPOINT_{name.upper()}_INVALID", "message": f"Every {name} row must be an object"})
    if not isinstance(checkpoint.get("research"), dict):
        issues.append({"code": "CHECKPOINT_RESEARCH_INVALID", "message": "research must be an object"})
    if not isinstance(checkpoint.get("angle"), dict):
        issues.append({"code": "CHECKPOINT_ANGLE_INVALID", "message": "angle must be an object"})
    else:
        angle = checkpoint["angle"]
        required_angle_fields = {
            name for name, field in AngleCandidate.model_fields.items()
            if field.is_required() and name not in {"angle_id"}
        }
        missing_angle_fields = sorted(required_angle_fields - set(angle))
        if missing_angle_fields:
            issues.append({
                "code": "ANGLE_FORMAL_FIELDS_MISSING",
                "message": "Missing required existing AngleCandidate fields: " + ", ".join(missing_angle_fields),
            })
    script = checkpoint.get("script")
    if not isinstance(script, dict) or not isinstance(script.get("text"), str) or not isinstance(script.get("sentences"), list):
        issues.append({"code": "CHECKPOINT_SCRIPT_INVALID", "message": "script must include text and sentence objects"})
    elif any(not isinstance(row, dict) for row in script["sentences"]):
        issues.append({"code": "CHECKPOINT_SCRIPT_SENTENCES_INVALID", "message": "Every script sentence must be an object"})
    return issues


def _dedupe_issues(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for item in issues:
        marker = (item.get("code"), item.get("message"))
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result


def _write_json(path: Path, value: Any) -> None:
    atomic_write_json(path, value)


def _write_text(path: Path, value: str) -> None:
    atomic_write_text(path, value)


def _angle_markdown(angle: dict[str, Any]) -> str:
    claims = "、".join(f"`{value}`" for value in angle.get("supporting_claim_ids", []))
    return (f"# 最终内容角度\n\nselected_angle_id: `{angle['angle_id']}`\n\n## 标题\n\n{angle['title']}\n\n"
            f"## 为什么值得讲\n\n{angle['core_question']}\n\n## 核心结论\n\n{angle['core_insight']}\n\n"
            f"## Claim 链\n\n{claims}\n\n## 不能说什么\n\n- 不得使用未验证事实或把精度差异包装成机构冲突。\n")


def _semantic_hashes(materialized: Path) -> dict[str, str]:
    result = {}
    if not materialized.is_dir():
        return result
    for name in ("approved_checkpoint.json", "id_mapping.json", "facts.json", "angles.json", "angle.md", "script.json", "script.md", "research.md", "sources.json"):
        path = materialized / name
        if not path.is_file():
            continue
        if path.suffix == ".json":
            value = json.loads(path.read_text("utf-8"))
            result[name] = _digest_json(_without_runtime(value, normalize_run_id=True))
        else:
            result[name] = sha256_text(path.read_text("utf-8"))
    return result


def _registry_write_json(registry: ArtifactRegistry, name: str, owner: str) -> None:
    registry.write_json(name, json.loads((registry.run_dir / name).read_text("utf-8")), owner)


def _registry_write_text(registry: ArtifactRegistry, name: str, owner: str) -> None:
    registry.write_text(name, (registry.run_dir / name).read_text("utf-8"), owner)
