"""Validated artifact contracts for Phase 1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


StageStatus = Literal["pending", "running", "succeeded", "failed", "stale"]
ArtifactStatus = Literal["missing", "valid", "stale", "failed"]


class ArtifactState(BaseModel):
    owner: str
    status: ArtifactStatus = "missing"
    content_hash: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    dependencies: dict[str, str] = Field(default_factory=dict)


class StageError(BaseModel):
    code: str
    message: str


class StageState(BaseModel):
    status: StageStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    input_sha256: str | None = None
    output_sha256: str | dict[str, str] | None = None
    provider: str | None = None
    prompt_version: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: StageError | None = None


class InputInfo(BaseModel):
    type: Literal["text", "markdown"]
    display_name: str
    sha256: str


class RunManifest(BaseModel):
    schema_version: str = "2.0"
    run_id: str
    created_at: str
    updated_at: str
    status: Literal[
        "created", "analyzed", "scripted", "visual_planned", "renderer_ready", "failed"
    ] = "created"
    input: InputInfo | None = None
    stages: dict[str, StageState] = Field(
        default_factory=lambda: {
            "ingest": StageState(),
            "analyze": StageState(),
        }
    )
    artifacts: dict[str, ArtifactState] = Field(default_factory=dict)


class ProviderInfo(BaseModel):
    name: str
    model: str | None = None
    prompt_version: str


class FactCandidate(BaseModel):
    id: str
    statement: str
    kind: str
    verification_required: bool


class AuthorArgument(BaseModel):
    id: str
    claim: str
    supporting_reasoning: str
    is_fact: bool = False


class VerificationClaim(BaseModel):
    id: str
    claim: str
    reason: str
    priority: Literal["low", "medium", "high"]


class ResearchQuestion(BaseModel):
    id: str
    question: str
    purpose: str
    expected_source_types: list[str]


class SingleSourceRisk(BaseModel):
    description: str
    related_claim_ids: list[str]
    severity: Literal["low", "medium", "high"]


class AnalysisResult(BaseModel):
    core_topic: str
    key_facts: list[FactCandidate]
    author_arguments: list[AuthorArgument]
    claims_requiring_external_verification: list[VerificationClaim]
    research_questions: list[ResearchQuestion]
    single_source_dependency_risks: list[SingleSourceRisk]
