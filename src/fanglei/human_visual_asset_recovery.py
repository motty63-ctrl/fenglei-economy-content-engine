"""Strict contracts for human review and visual-only asset recovery."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

from fanglei.errors import ArtifactConflictError
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.visual_models import Placement, Storyboard


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIGNED_DISPLAY_VALUE = re.compile(
    r"^(?P<sign>[+＋\-−])(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)(?P<unit>\s*[^\d\s].*)?$"
)
_TONES = Literal["primary", "secondary", "muted", "positive", "negative", "neutral"]


def _aware_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


def _validate_hash_map(values: dict[str, str]) -> dict[str, str]:
    if not values or any(not key.strip() or not _SHA256.fullmatch(digest) for key, digest in values.items()):
        raise ValueError("dependency hashes must be named lowercase SHA-256 values")
    return values


class HumanVisualAssetReviewV1(BaseModel):
    """A human decision tied to one immutable visual candidate and its inputs."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["human-visual-asset-review/1.0"]
    candidate_id: StrictInt = Field(gt=0)
    decision: Literal["changes_required", "approved_for_timeline"]
    run_id: StrictStr = Field(min_length=1)
    case_id: StrictStr = Field(min_length=1)
    reviewer: StrictStr = Field(min_length=1)
    reviewed_at: StrictStr = Field(min_length=1)
    reason_code: StrictStr = Field(min_length=1)
    rationale: StrictStr = Field(min_length=1)
    findings: list[StrictStr] = Field(min_length=1)
    storyboard_sha256: StrictStr
    storyboard_artifact_sha256: StrictStr
    storyboard_approval_sha256: StrictStr
    visual_bundle_sha256: StrictStr
    dependency_hashes: dict[StrictStr, StrictStr]

    @field_validator("run_id", "case_id", "reviewer", "reason_code", "rationale")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("findings")
    @classmethod
    def findings_are_nonblank(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("findings must not be blank")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def timestamp_is_aware(cls, value: str) -> str:
        return _aware_timestamp(value)

    @field_validator(
        "storyboard_sha256", "storyboard_artifact_sha256", "storyboard_approval_sha256",
        "visual_bundle_sha256",
    )
    @classmethod
    def hash_is_valid(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("dependency_hashes")
    @classmethod
    def hashes_are_valid(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_hash_map(value)

    @model_validator(mode="after")
    def explicit_bindings_match(self) -> "HumanVisualAssetReviewV1":
        bindings = {
            "human_storyboard_candidate.json": self.storyboard_artifact_sha256,
            "human_storyboard_approval.json": self.storyboard_approval_sha256,
            "visual_assets" if self.candidate_id == 1 else f"visual_assets_candidate_{self.candidate_id}":
                self.visual_bundle_sha256,
        }
        for name, digest in bindings.items():
            if self.dependency_hashes.get(name) != digest:
                raise ValueError(f"dependency hash does not match reviewed {name}")
        return self


class VisualObjectStyleV1(BaseModel):
    """Presentation-only overrides for an existing Storyboard object."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    object_id: StrictStr = Field(min_length=1)
    placement: Placement
    target_font_size: StrictInt = Field(ge=16, le=240)
    tone: _TONES
    show_card: bool

    @field_validator("object_id")
    @classmethod
    def object_id_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("object_id must not be blank")
        return value


class VisualDecorationV1(BaseModel):
    """Text-free geometric decoration that cannot introduce a proposition."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: Literal["line", "circle", "rect"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    rotation_degrees: StrictInt = Field(ge=0, le=359)
    tone: _TONES
    opacity: float = Field(gt=0, le=0.35)
    stroke_width: StrictInt = Field(ge=1, le=24)
    filled: bool

    @model_validator(mode="after")
    def within_mobile_safe_area(self) -> "VisualDecorationV1":
        if self.x < 0.05 or self.y < 0.04 or self.x + self.width > 0.95 or self.y + self.height > 0.90:
            raise ValueError("decorations must stay inside the mobile safe area")
        return self


class DivergingBarV1(BaseModel):
    """A sign-and-magnitude bar bound to existing label/value objects."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    label_object_id: StrictStr = Field(min_length=1)
    value_object_id: StrictStr = Field(min_length=1)
    center_x: float = Field(ge=0.25, le=0.75)
    y: float = Field(ge=0.08, le=0.86)
    max_half_width: float = Field(gt=0, le=0.42)
    height: float = Field(gt=0, le=0.08)

    @model_validator(mode="after")
    def bar_stays_in_safe_area(self) -> "DivergingBarV1":
        if self.center_x - self.max_half_width < 0.05 or self.center_x + self.max_half_width > 0.95:
            raise ValueError("diverging bar exceeds the mobile safe area")
        if self.y + self.height > 0.90:
            raise ValueError("diverging bar exceeds the mobile safe area")
        return self


class VisualSceneLayoutV1(BaseModel):
    """Reusable visual archetype plus complete style mapping for one scene."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    scene_id: StrictStr = Field(min_length=1)
    order: StrictInt = Field(ge=1)
    profile: Literal[
        "hero_topics", "split_metrics", "metric_focus", "revision_flow",
        "diverging_comparison", "category_grid", "closing_card",
    ]
    object_styles: list[VisualObjectStyleV1] = Field(min_length=1)
    decorations: list[VisualDecorationV1]
    diverging_bars: list[DivergingBarV1]

    @model_validator(mode="after")
    def object_ids_are_unique(self) -> "VisualSceneLayoutV1":
        ids = [style.object_id for style in self.object_styles]
        if len(ids) != len(set(ids)):
            raise ValueError("object styles must have unique object IDs")
        bar_ids = [bar.value_object_id for bar in self.diverging_bars]
        if len(bar_ids) != len(set(bar_ids)):
            raise ValueError("a value object may only appear in one diverging bar")
        return self


class VisualSourceFooterV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    label: StrictStr = Field(min_length=1)
    source_ids: list[StrictStr] = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def label_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source footer label must not be blank")
        return value

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("source footer IDs must be nonblank and unique")
        return value


class VisualAssetRecoveryPlanV1(BaseModel):
    """Hash-bound style/layout edit; it intentionally has no copy or claim fields."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["visual-asset-recovery/1.0"]
    run_id: StrictStr = Field(min_length=1)
    case_id: StrictStr = Field(min_length=1)
    source_candidate_id: StrictInt = Field(gt=0)
    candidate_id: StrictInt = Field(gt=1)
    recovery_rationale: StrictStr = Field(min_length=1)
    storyboard_sha256: StrictStr
    storyboard_artifact_sha256: StrictStr
    storyboard_approval_sha256: StrictStr
    source_visual_bundle_sha256: StrictStr
    source_review_sha256: StrictStr
    dependency_hashes: dict[StrictStr, StrictStr]
    source_footer: VisualSourceFooterV1
    scene_layouts: list[VisualSceneLayoutV1] = Field(min_length=1)

    @field_validator("run_id", "case_id", "recovery_rationale")
    @classmethod
    def identity_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator(
        "storyboard_sha256", "storyboard_artifact_sha256", "storyboard_approval_sha256",
        "source_visual_bundle_sha256", "source_review_sha256",
    )
    @classmethod
    def digest_is_valid(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("dependency_hashes")
    @classmethod
    def dependencies_are_valid(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_hash_map(value)

    @model_validator(mode="after")
    def sequential_candidate_identity(self) -> "VisualAssetRecoveryPlanV1":
        if self.candidate_id != self.source_candidate_id + 1:
            raise ValueError("recovery candidate ID must advance exactly once")
        bindings = {
            "human_visual_asset_review_candidate_1.json": self.source_review_sha256,
            "human_storyboard_candidate.json": self.storyboard_artifact_sha256,
            "human_storyboard_approval.json": self.storyboard_approval_sha256,
            "visual_assets" if self.source_candidate_id == 1 else f"visual_assets_candidate_{self.source_candidate_id}":
                self.source_visual_bundle_sha256,
        }
        for name, digest in bindings.items():
            if self.dependency_hashes.get(name) != digest:
                raise ValueError(f"dependency hash does not match {name}")
        return self


def parse_signed_display_value(value: str) -> tuple[Decimal, str, str]:
    """Parse an explicitly signed display value for non-semantic bar geometry only."""
    match = _SIGNED_DISPLAY_VALUE.fullmatch(value.strip())
    if match is None:
        raise ArtifactConflictError("VISUAL_ASSET_BAR_VALUE_MUST_BE_EXPLICITLY_SIGNED")
    try:
        amount = Decimal(match.group("number").replace(",", ""))
    except InvalidOperation as error:
        raise ArtifactConflictError("VISUAL_ASSET_BAR_VALUE_INVALID") from error
    sign = "negative" if match.group("sign") in {"-", "−"} else "positive"
    return amount, (match.group("unit") or "").strip(), sign


def validate_visual_asset_recovery_plan(
    storyboard: Storyboard,
    review: HumanVisualAssetReviewV1,
    plan: VisualAssetRecoveryPlanV1,
    *,
    current_visual_bundle_sha256: str,
    current_dependency_hashes: dict[str, str],
    approved_source_ids: set[str],
) -> None:
    """Fail closed unless a style-only plan matches the reviewed candidate exactly."""
    story_sha = canonical_json_sha256(storyboard)
    if (
        storyboard.run_id != plan.run_id or review.run_id != plan.run_id
        or review.case_id != plan.case_id or storyboard.run_id != review.run_id
    ):
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_IDENTITY_MISMATCH")
    if review.candidate_id != plan.source_candidate_id or review.decision != "changes_required":
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_REVIEW_NOT_CHANGES_REQUIRED")
    if plan.storyboard_sha256 != story_sha or review.storyboard_sha256 != story_sha:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_STORYBOARD_MISMATCH")
    if plan.storyboard_artifact_sha256 != review.storyboard_artifact_sha256:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_STORYBOARD_ARTIFACT_MISMATCH")
    if (
        current_visual_bundle_sha256 != plan.source_visual_bundle_sha256
        or current_visual_bundle_sha256 != review.visual_bundle_sha256
    ):
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SOURCE_BUNDLE_MISMATCH")
    if plan.source_review_sha256 != current_dependency_hashes.get("human_visual_asset_review_candidate_1.json"):
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_REVIEW_HASH_MISMATCH")
    if review.storyboard_approval_sha256 != plan.storyboard_approval_sha256:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_APPROVAL_MISMATCH")
    if plan.dependency_hashes != current_dependency_hashes:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_DEPENDENCIES_STALE")
    if plan.source_footer.source_ids != sorted(plan.source_footer.source_ids):
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SOURCE_IDS_NOT_CANONICAL")
    if not set(plan.source_footer.source_ids) <= approved_source_ids:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SOURCE_FOOTER_NOT_APPROVED")

    if len(plan.scene_layouts) != len(storyboard.scenes) or [row.scene_id for row in plan.scene_layouts] != [
        scene.scene_id for scene in storyboard.scenes
    ]:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SCENE_COVERAGE_INVALID")
    for scene, layout in zip(storyboard.scenes, plan.scene_layouts, strict=True):
        if layout.order != scene.order or layout.scene_id != scene.scene_id:
            raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SCENE_ORDER_CHANGED")
        storyboard_objects = {obj.object_id: obj for obj in scene.objects}
        style_objects = {style.object_id: style for style in layout.object_styles}
        if set(style_objects) != set(storyboard_objects):
            raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_OBJECT_COVERAGE_INVALID")
        for style in layout.object_styles:
            box = style.placement
            if box.x < 0.05 or box.y < 0.04 or box.x + box.width > 0.95 or box.y + box.height > 0.90:
                raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_OBJECT_OUTSIDE_SAFE_AREA")
        for bar in layout.diverging_bars:
            label = storyboard_objects.get(bar.label_object_id)
            value = storyboard_objects.get(bar.value_object_id)
            if label is None or value is None:
                raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_BAR_OBJECT_UNKNOWN")
            if (
                not label.claim_ids or label.claim_ids != value.claim_ids
                or label.sentence_ids != value.sentence_ids
            ):
                raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_BAR_BINDING_MISMATCH")
        if layout.diverging_bars:
            parsed = [
                parse_signed_display_value(storyboard_objects[bar.value_object_id].content)
                for bar in layout.diverging_bars
            ]
            if len({unit for _, unit, _ in parsed}) != 1:
                raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_BAR_UNITS_MISMATCH")
