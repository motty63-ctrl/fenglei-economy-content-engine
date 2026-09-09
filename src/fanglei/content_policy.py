"""Fact whitelist for V0.3 content generation."""
from fanglei.content_models import ScriptReadyClaim
from fanglei.evidence_policy import is_script_ready


def build_fact_palette(facts: dict) -> tuple[ScriptReadyClaim, ...]:
    ready = []
    for claim in facts.get("claims", []):
        if claim.get("claim_type") != "fact" or not is_script_ready(claim):
            continue
        evidence = [item for item in claim.get("evidence", []) if item.get("evidence_eligible")]
        if not evidence:
            continue
        ready.append(ScriptReadyClaim(
            claim_id=claim["claim_id"], claim_text=claim["claim_text"],
            source_ids=claim.get("source_ids", []), evidence=evidence,
        ))
    return tuple(ready)
