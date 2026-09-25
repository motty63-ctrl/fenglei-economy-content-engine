"""Typed V0.3 content planning contracts."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class ScriptReadyClaim(BaseModel):
    claim_id: str
    claim_text: str
    source_ids: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    verification_basis: Literal[
        "independent_corroboration", "authoritative_primary_attestation", "none"
    ] = "independent_corroboration"
    authority_attestation: dict[str, Any] | None = None


class AngleProposal(BaseModel):
    angle_id: str
    title: str
    hook: str
    core_question: str
    core_insight: str
    hook_mechanism: str = "unspecified"
    audience_takeaway: str = "unspecified"
    narrative_framing: str = "unspecified"
    supporting_claim_ids: list[str]
    audience_relevance: int = Field(ge=0, le=5)
    novelty: int = Field(ge=0, le=5)
    hook_strength: int = Field(ge=0, le=5)
    visual_potential: int = Field(ge=0, le=5)
    explainability: int = Field(ge=0, le=5)
    risk_notes: list[str] = Field(default_factory=list)


class AngleCandidate(AngleProposal):
    evidence_strength: int = Field(ge=0, le=5)
    controversy_risk: int = Field(ge=0, le=5)
    total_score: int = Field(ge=0, le=100)
    eligibility: Literal["eligible", "rejected"]
    rejection_codes: list[str] = Field(default_factory=list)
    originality: dict[str, Any] = Field(default_factory=dict)


class AngleProposalResult(BaseModel):
    candidates: list[AngleProposal]


class AngleDiversityResult(BaseModel):
    passed: bool
    candidate_count: int
    distinct_core_questions: int
    distinct_hooks: int
    distinct_hook_mechanisms: int
    distinct_audience_takeaways: int
    distinct_framings: int
    issue_codes: list[str] = Field(default_factory=list)


class ScriptSentence(BaseModel):
    sentence_id: str
    section: Literal["hook", "phenomenon", "mechanism", "core_judgment"]
    sentence_type: Literal["verified_fact", "explanation", "interpretation", "analogy"]
    text: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def claims_match_type(self) -> "ScriptSentence":
        if self.sentence_type == "verified_fact" and not self.claim_ids:
            raise ValueError("verified_fact requires claim_ids")
        return self


class ScriptDraft(BaseModel):
    schema_version: Literal["3.0"] = "3.0"
    script_id: str = "script_001"
    angle_id: str
    title: str
    target_duration_seconds: int = Field(default=75, ge=60, le=90)
    sentences: list[ScriptSentence]


class LintIssue(BaseModel):
    code: str
    message: str
    sentence_id: str | None = None
    severity: Literal["error", "warning"] = "error"


class ScriptLintResult(BaseModel):
    passed: bool
    speaking_rate_chars_per_second: float
    spoken_character_count: int
    estimated_duration_seconds: float
    issues: list[LintIssue] = Field(default_factory=list)
