"""Fact whitelist for V0.3 content generation."""
from fanglei.content_models import ScriptReadyClaim
from fanglei.evidence_policy import is_script_ready


def build_fact_palette(facts: dict) -> tuple[ScriptReadyClaim, ...]:
    ready = []
    for claim in facts.get("claims", []):
        if claim.get("claim_type") != "fact" or not is_script_ready(claim):
            continue
        source_ids = set(claim.get("source_ids", []))
        evidence = [item for item in claim.get("evidence", [])
                    if item.get("evidence_eligible")
                    and item.get("source_id") in source_ids
                    and item.get("original_url")
                    and (item.get("evidence_text") or item.get("observation") is not None
                         or item.get("value") is not None)]
        if not evidence:
            continue
        ready.append(ScriptReadyClaim(
            claim_id=claim["claim_id"], claim_text=claim["claim_text"],
            source_ids=claim.get("source_ids", []), evidence=evidence,
        ))
    return tuple(ready)
