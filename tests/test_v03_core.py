import pytest
from pydantic import ValidationError

from fanglei.artifact_registry import ARTIFACT_GRAPH
from fanglei.content_models import ScriptSentence
from fanglei.content_policy import build_fact_palette


def test_v03_artifacts_have_separate_owners_and_dependencies() -> None:
    assert ARTIFACT_GRAPH["angles.json"] == (
        "angle_generation", ("facts.json", "research.md", "questions.json", "source.md")
    )
    assert ARTIFACT_GRAPH["angle.md"] == ("angle_selection", ("angles.json", "facts.json"))
    assert ARTIFACT_GRAPH["script.json"] == (
        "script_generation", ("angle.md", "facts.json", "research.md", "source.md")
    )
    assert ARTIFACT_GRAPH["script.md"] == ("script_render", ("script.json",))


def test_verified_fact_requires_claim_and_other_types_may_bind_for_semantic_gate() -> None:
    with pytest.raises(ValidationError):
        ScriptSentence(sentence_id="sentence_001", section="phenomenon",
                       sentence_type="verified_fact", text="增长2.8%。", claim_ids=[])
    sentence = ScriptSentence(sentence_id="sentence_002", section="mechanism",
                              sentence_type="explanation", text="这是舍入差异。", claim_ids=["claim_001"])
    assert sentence.claim_ids == ["claim_001"]


def test_fact_palette_excludes_unverified_conflicted_and_disallowed() -> None:
    facts = {"claims": [
        {"claim_id": "claim_001", "claim_text": "增长2.8%", "claim_type": "fact",
         "verification_status": "verified", "allowed_downstream": True,
         "source_ids": ["src_1", "src_2"], "evidence": [{"source_id": "src_1", "original_url": "https://example.test/data", "evidence_text": "增长2.8%", "evidence_eligible": True}]},
        {"claim_id": "claim_002", "claim_text": "增长3%", "claim_type": "fact",
         "verification_status": "conflicted", "allowed_downstream": False, "evidence": []},
        {"claim_id": "claim_003", "claim_text": "增长4%", "claim_type": "fact",
         "verification_status": "unverified", "allowed_downstream": False, "evidence": []},
    ]}
    palette = build_fact_palette(facts)
    assert [claim.claim_id for claim in palette] == ["claim_001"]


def test_fact_palette_excludes_incomplete_evidence_provenance() -> None:
    facts = {"claims": [{"claim_id": "claim_broken", "claim_text": "美国2024年实际GDP增长2.8%",
        "claim_type": "fact", "verification_status": "verified", "allowed_downstream": True,
        "source_ids": ["src_1"], "evidence": [{"source_id": "src_1", "evidence_eligible": True}]}]}
    assert build_fact_palette(facts) == ()


def test_fact_palette_requires_evidence_source_to_match_claim_sources() -> None:
    facts = {"claims": [{"claim_id": "claim_broken", "claim_text": "增长2.8%",
        "claim_type": "fact", "verification_status": "verified", "allowed_downstream": True,
        "source_ids": ["src_1"], "evidence": [{"source_id": "src_other",
        "original_url": "https://example.test/data", "evidence_text": "增长2.8%", "evidence_eligible": True}]}]}
    assert build_fact_palette(facts) == ()
