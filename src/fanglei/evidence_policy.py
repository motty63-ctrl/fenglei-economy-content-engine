"""Evidence provenance and downstream-script eligibility gates."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.providers.official import request_fingerprint
from fanglei.security import sanitize_url

if TYPE_CHECKING:
    from fanglei.research import FetchedDocument


def _json_pointer(value: object, pointer: str) -> object:
    current = value
    if not pointer.startswith("/"):
        raise ValueError("invalid JSON pointer")
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]  # type: ignore[index]
    return current


def gate_evidence(evidence: list[dict[str, Any]], documents: list["FetchedDocument"]) -> list[dict[str, Any]]:
    by_id = {document.source_id: document for document in documents}
    gated: list[dict[str, Any]] = []
    for item in evidence:
        result = dict(item)
        document = by_id.get(item.get("source_id"))
        eligible = False
        reason = "source_document_missing"
        if item.get("evidence_origin") == "search_snippet":
            reason = "search_snippet_ineligible"
        elif document is None:
            reason = "source_document_missing"
        elif not document.evidence_eligible:
            reason = document.eligibility_reason or "source_document_ineligible"
        elif item.get("document_hash") != document.document_hash:
            reason = "document_hash_mismatch"
        elif item.get("evidence_text") not in document.text:
            reason = "evidence_text_not_in_document"
        elif document.document_format == "api":
            try:
                if not document.raw_content or sha256_text(document.raw_content) != document.document_hash:
                    raise ValueError("raw API response hash mismatch")
                if not item.get("api_endpoint") or sanitize_url(item["api_endpoint"]) != item["api_endpoint"]:
                    raise ValueError("unsafe API endpoint")
                if item.get("request_fingerprint") != request_fingerprint(item["api_endpoint"]):
                    raise ValueError("request fingerprint mismatch")
                resolved = _json_pointer(json.loads(document.raw_content), item.get("json_pointer") or "")
                if resolved != item.get("observation"):
                    raise ValueError("observation mismatch")
                eligible, reason = True, "api_observation_resolved"
            except Exception:
                reason = "api_observation_unresolved"
        elif document.document_format == "pdf":
            page = next(
                (page for page in document.pages if page.get("page_number") == item.get("page_number")),
                None,
            )
            if (
                document.raw_bytes is not None
                and sha256_bytes(document.raw_bytes) == document.document_hash
                and page
                and page.get("content_hash") == item.get("page_content_hash")
                and item.get("evidence_text") in str(page.get("text", ""))
            ):
                eligible, reason = True, "pdf_page_resolved"
            else:
                reason = "pdf_page_unresolved"
        else:
            eligible, reason = True, "document_text_resolved"
        result["evidence_eligible"] = eligible
        result["eligibility_reason"] = reason
        gated.append(result)
    return gated


def claim_eligibility_reason(claim: object) -> str:
    """Return the shared fail-closed content-eligibility reason for a claim.

    The contract intentionally checks recorded verification status and the
    explicit downstream permission independently. Authority attribution/scope
    checks remain with the existing stage-specific safety validators.
    """
    if isinstance(claim, Mapping):
        record = claim
    else:
        dump = getattr(claim, "model_dump", None)
        if not callable(dump):
            return "invalid_claim"
        try:
            record = dump(mode="python")
        except Exception:
            return "invalid_claim"
        if not isinstance(record, Mapping):
            return "invalid_claim"

    status = record.get("verification_status")
    if status == "unverified":
        return "unverified"
    if status == "conflicted":
        return "conflicted"
    if status != "verified":
        return "invalid_status"
    if record.get("allowed_downstream") is not True:
        return "downstream_not_allowed"
    return "eligible"


def is_claim_eligible_for_content(claim: object) -> bool:
    """Whether a claim may enter the V0.2 content path."""
    return claim_eligibility_reason(claim) == "eligible"


def is_script_ready(claim: dict[str, Any]) -> bool:
    """Compatibility alias for the shared content eligibility predicate."""
    return is_claim_eligible_for_content(claim)


def script_usage(status: str) -> dict[str, str]:
    if status == "verified":
        return {"status": "assertion_allowed", "reason": "verified economic fact"}
    if status == "conflicted":
        return {"status": "blocked", "reason": "independent sources disagree"}
    return {
        "status": "disclosure_only",
        "required_label": "待确认",
        "reason": "insufficient eligible evidence",
    }
