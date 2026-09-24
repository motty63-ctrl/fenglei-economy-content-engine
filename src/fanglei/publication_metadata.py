"""Human-reviewed publication dates bound to normalized source captures."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated
from typing import Any, Literal, Mapping

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from fanglei.artifacts import sha256_text


class PublicationMetadataError(ValueError):
    """A publication-date review does not match its normalized source capture."""


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1), AfterValidator(_nonblank)]
Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def _aware_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("must be a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


AwareTimestamp = Annotated[NonBlank, AfterValidator(_aware_timestamp)]


class PublicationDateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    locator: NonBlank
    excerpt: NonBlank

    @field_validator("locator")
    @classmethod
    def require_line_locator(cls, value: str) -> str:
        if re.fullmatch(r"line:[1-9][0-9]*", value) is None:
            raise ValueError("locator must use the stable line:<one-based-line-number> format")
        return value

    @classmethod
    def _line_number(cls, locator: str) -> int:
        match = re.fullmatch(r"line:([1-9][0-9]*)", locator)
        if match is None:
            raise ValueError("locator must use the stable line:<one-based-line-number> format")
        return int(match.group(1))


class PublicationDateReviewV1(BaseModel):
    """Strict human decision bound to a source identity and exact text hash."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["publication-date-review/1.0"]
    status: Literal["approved"]
    reviewer: NonBlank
    reviewed_at: AwareTimestamp
    published_at: NonBlank
    source_id: NonBlank
    url: NonBlank
    source_text_sha256: Sha256
    evidence: list[PublicationDateEvidence] = Field(min_length=1)
    rationale: NonBlank

    @field_validator("published_at")
    @classmethod
    def require_canonical_date(cls, value: str) -> str:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError("published_at must use canonical YYYY-MM-DD format")
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("published_at must be a valid calendar date") from error
        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError("published_at must use canonical YYYY-MM-DD format")
        return value


def _parse_review(review: PublicationDateReviewV1 | Mapping[str, Any]) -> PublicationDateReviewV1:
    payload = review.model_dump(mode="python") if isinstance(review, PublicationDateReviewV1) else review
    return PublicationDateReviewV1.model_validate(payload)


def validate_publication_date_review(
    review: PublicationDateReviewV1 | Mapping[str, Any],
    *,
    source_id: str,
    url: str,
    source_text: str,
) -> PublicationDateReviewV1:
    """Validate review identity, normalized-text hash, line locator, and excerpt."""
    try:
        parsed = _parse_review(review)
    except Exception as error:
        raise PublicationMetadataError(f"invalid publication-date review: {error}") from error
    if parsed.source_id != source_id or parsed.url != url:
        raise PublicationMetadataError("publication-date review source identity does not match the index row")
    if parsed.source_text_sha256 != sha256_text(source_text):
        raise PublicationMetadataError("publication-date review source_text_sha256 does not match the normalized capture")
    lines = source_text.splitlines()
    for evidence in parsed.evidence:
        try:
            line_number = PublicationDateEvidence._line_number(evidence.locator)
        except ValueError as error:
            raise PublicationMetadataError(str(error)) from error
        if line_number > len(lines):
            raise PublicationMetadataError(f"publication-date evidence locator is outside the normalized capture: {evidence.locator}")
        if evidence.excerpt not in lines[line_number - 1]:
            raise PublicationMetadataError(f"publication-date evidence excerpt does not match {evidence.locator}")
    return parsed


def apply_publication_date_reviews_to_index(
    index: Mapping[str, Any],
    reviews: list[PublicationDateReviewV1 | Mapping[str, Any]],
    *,
    normalized_text_by_source_id: Mapping[str, str],
) -> dict[str, Any]:
    """Return an index copy with validated reviews; never infer review fields."""
    if not reviews:
        raise PublicationMetadataError("at least one explicit publication-date review is required")
    documents = index.get("documents")
    if not isinstance(documents, list) or any(not isinstance(row, Mapping) for row in documents):
        raise PublicationMetadataError("source document index must contain a documents array")
    rows_by_id = {row.get("source_id"): row for row in documents}
    if len(rows_by_id) != len(documents) or None in rows_by_id:
        raise PublicationMetadataError("source document index must have unique non-empty source IDs")

    parsed_reviews: dict[str, PublicationDateReviewV1] = {}
    for review in reviews:
        try:
            parsed = _parse_review(review)
        except Exception as error:
            raise PublicationMetadataError(f"invalid publication-date review: {error}") from error
        if parsed.source_id in parsed_reviews:
            raise PublicationMetadataError(f"duplicate publication-date review for {parsed.source_id}")
        row = rows_by_id.get(parsed.source_id)
        if row is None:
            raise PublicationMetadataError(f"publication-date review references an unknown source: {parsed.source_id}")
        text = normalized_text_by_source_id.get(parsed.source_id)
        if not isinstance(text, str):
            raise PublicationMetadataError(f"normalized capture is missing for {parsed.source_id}")
        if row.get("content_hash") != sha256_text(text):
            raise PublicationMetadataError(
                f"source index content_hash does not match the normalized capture for {parsed.source_id}"
            )
        parsed_reviews[parsed.source_id] = validate_publication_date_review(
            parsed,
            source_id=row.get("source_id"),
            url=row.get("url"),
            source_text=text,
        )

    rebuilt = {key: value for key, value in index.items()}
    rebuilt_documents: list[dict[str, Any]] = []
    for original in documents:
        row = dict(original)
        review = parsed_reviews.get(row.get("source_id"))
        if review is not None:
            serialized_review = review.model_dump(mode="json")
            existing_review = row.get("publication_date_review")
            if existing_review is not None:
                try:
                    previous = _parse_review(existing_review)
                except Exception as error:
                    raise PublicationMetadataError(
                        f"existing publication-date review is malformed for {review.source_id}"
                    ) from error
                if previous.model_dump(mode="json") != serialized_review:
                    raise PublicationMetadataError(
                        f"publication-date review is write-once for {review.source_id}"
                    )
            existing_date = row.get("published_at")
            if existing_date is not None and existing_date != review.published_at:
                raise PublicationMetadataError(
                    f"reviewed publication date conflicts with existing capture metadata for {review.source_id}"
                )
            row["published_at"] = review.published_at
            row["publication_date_review"] = serialized_review
        rebuilt_documents.append(row)
    rebuilt["documents"] = rebuilt_documents
    return rebuilt
