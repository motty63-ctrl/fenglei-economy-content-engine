import hashlib
import json
from pathlib import Path

import pytest

import fanglei.pipeline as pipeline
from fanglei.errors import ArtifactConflictError
from fanglei.publication_metadata import PublicationDateReviewV1
from fanglei.pipeline import run_v02_pipeline
from fanglei.providers.mock import MockAnalysisProvider
from fanglei.providers.search import SearchRequest, SearchResponse, SearchResult
from fanglei.research import FetchedDocument
from fanglei.stages.analyze import analyze_run
from fanglei.stages.ingest import ingest_text


def _apply_reviews(run_id: str, runs_dir: Path, reviews: list[dict]) -> Path:
    action = getattr(pipeline, "apply_publication_date_reviews", None)
    if action is None:
        pytest.fail("missing offline publication-date review owner API")
    return action(run_id, runs_dir, reviews)


def _rebuild_sources(run_id: str, runs_dir: Path) -> Path:
    action = getattr(pipeline, "rebuild_source_selection_from_index", None)
    if action is None:
        pytest.fail("missing offline source-selection rebuild API")
    return action(run_id, runs_dir)


class _Search:
    name = "local-fixture"

    def search(self, request: SearchRequest) -> SearchResponse:
        results = [
            SearchResult(f"https://source{i}.example/page", f"Source {i}", "discovery only")
            for i in range(1, 4)
        ]
        return SearchResponse(request.query, self.name, results)


class _Fetcher:
    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument:
        index = int(source_id[-1])
        text = f"Source {index}\nPublished: June 17, 2026\nEvidence body {index}."
        source_types = ["official", "international_organization", "company_disclosure"]
        return FetchedDocument(
            source_id=source_id,
            url=url,
            title=title,
            text=text,
            source_type=source_types[index - 1],
            published_at=None,
            retrieved_at="2026-09-24T12:00:00+00:00",
            raw_content=json.dumps({"captured_source": index}),
        )


def _source_run(tmp_path: Path) -> Path:
    run = ingest_text("# Offline publication review\nSource review fixture.", tmp_path)
    analyze_run(run.name, tmp_path, MockAnalysisProvider())
    run_v02_pipeline(run.name, tmp_path, _Search(), _Fetcher(), stop_after="source_selection")
    return run


def _review(run: Path, source_id: str = "src_001") -> dict:
    index = json.loads((run / "source_documents" / "index.json").read_text(encoding="utf-8"))
    row = next(item for item in index["documents"] if item["source_id"] == source_id)
    text = (run / row["path"]).read_text(encoding="utf-8")
    return {
        "schema_version": "publication-date-review/1.0",
        "status": "approved",
        "reviewer": "reviewer@example.test",
        "reviewed_at": "2026-09-24T14:00:00+08:00",
        "published_at": "2026-06-17",
        "source_id": source_id,
        "url": row["url"],
        "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "evidence": [
            {"locator": "line:2", "excerpt": "Published: June 17, 2026"}
        ],
        "rationale": "The normalized capture explicitly labels this date as the publication date.",
    }


def test_reviewed_publication_date_updates_index_and_invalidates_only_sources(tmp_path: Path) -> None:
    run = _source_run(tmp_path)
    manifest_before = json.loads((run / "run.json").read_text(encoding="utf-8"))
    index_before = manifest_before["artifacts"]["source_documents/index.json"]["content_hash"]
    source_md_before = {
        path.name: path.read_bytes() for path in (run / "source_documents").glob("src_*.md")
    }
    index_before_json = json.loads((run / "source_documents" / "index.json").read_text(encoding="utf-8"))
    text_hashes_before = {row["source_id"]: row["content_hash"] for row in index_before_json["documents"]}
    identities_before = {row["source_id"]: row["url"] for row in index_before_json["documents"]}
    indexed_files_before = {row["source_id"]: row["files"] for row in index_before_json["documents"]}
    source_assets_before = {
        path.relative_to(run / "source_documents").as_posix(): path.read_bytes()
        for path in (run / "source_documents").rglob("*")
        if path.is_file() and path.name != "index.json"
    }
    upstream_before = {
        name: manifest_before["artifacts"][name]["content_hash"]
        for name in ("source.md", "questions.json", "search_results.json")
    }

    _apply_reviews(run.name, tmp_path, [_review(run)])

    manifest_after = json.loads((run / "run.json").read_text(encoding="utf-8"))
    index_after = json.loads((run / "source_documents" / "index.json").read_text(encoding="utf-8"))
    reviewed = next(row for row in index_after["documents"] if row["source_id"] == "src_001")
    assert reviewed["published_at"] == "2026-06-17"
    assert reviewed["publication_date_review"]["schema_version"] == "publication-date-review/1.0"
    assert reviewed["content_hash"] == text_hashes_before["src_001"]
    assert {row["source_id"]: row["content_hash"] for row in index_after["documents"]} == text_hashes_before
    assert {row["source_id"]: row["url"] for row in index_after["documents"]} == identities_before
    assert {row["source_id"]: row["files"] for row in index_after["documents"]} == indexed_files_before
    assert {
        path.relative_to(run / "source_documents").as_posix(): path.read_bytes()
        for path in (run / "source_documents").rglob("*")
        if path.is_file() and path.name != "index.json"
    } == source_assets_before
    assert manifest_after["artifacts"]["source_documents/index.json"]["status"] == "valid"
    assert manifest_after["artifacts"]["source_documents/index.json"]["content_hash"] != index_before
    assert manifest_after["artifacts"]["sources.json"]["status"] == "stale"
    assert manifest_after["artifacts"]["facts.json"]["status"] == "missing"
    assert manifest_after["artifacts"]["research.md"]["status"] == "missing"
    assert {
        name: manifest_after["artifacts"][name]["content_hash"] for name in upstream_before
    } == upstream_before
    assert all(manifest_after["artifacts"][name]["status"] == "valid" for name in upstream_before)
    assert {
        path.name: path.read_bytes() for path in (run / "source_documents").glob("src_*.md")
    } == source_md_before


def test_source_selection_rebuild_is_offline_and_uses_reviewed_index_date(tmp_path: Path) -> None:
    run = _source_run(tmp_path)
    before = {
        path.name: path.read_bytes() for path in (run / "source_documents").glob("src_*.md")
    }
    _apply_reviews(run.name, tmp_path, [_review(run)])

    _rebuild_sources(run.name, tmp_path)

    sources = json.loads((run / "sources.json").read_text(encoding="utf-8"))
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    source = next(row for row in sources["sources"] if row["source_id"] == "src_001")
    index_hash = manifest["artifacts"]["source_documents/index.json"]["content_hash"]
    assert source["published_at"] == "2026-06-17"
    assert manifest["artifacts"]["sources.json"]["status"] == "valid"
    assert manifest["artifacts"]["sources.json"]["dependencies"]["source_documents/index.json"] == index_hash
    assert {
        path.name: path.read_bytes() for path in (run / "source_documents").glob("src_*.md")
    } == before


@pytest.mark.parametrize(
    "change",
    [
        lambda review: review.update(source_text_sha256="0" * 64),
        lambda review: review["evidence"][0].update(locator="line:99"),
        lambda review: review["evidence"][0].update(excerpt="not in the capture"),
        lambda review: review.update(published_at="June 17, 2026"),
        lambda review: review.update(reviewed_at="2026-09-24T14:00:00"),
        lambda review: review.update(reviewer=" "),
        lambda review: review.update(rationale=""),
        lambda review: review.update(evidence=[]),
        lambda review: review.update(source_id="src_999"),
        lambda review: review.update(url="https://different.example/page"),
        lambda review: review.update(schema_version="publication-date-review/2.0"),
        lambda review: review.update(status="draft"),
        lambda review: review.update(unreviewed_guess=True),
        lambda review: review.pop("reviewer"),
        lambda review: review.pop("rationale"),
        lambda review: review.pop("evidence"),
    ],
    ids=[
        "stale-source-hash", "bad-locator", "excerpt-mismatch", "malformed-date",
        "naive-review-time", "missing-reviewer", "missing-rationale", "missing-evidence",
        "source-id-mismatch", "url-mismatch", "wrong-schema-version", "not-approved", "unknown-field",
        "missing-reviewer", "missing-rationale", "missing-evidence",
    ],
)
def test_invalid_review_fails_without_rewriting_index_or_sources(tmp_path: Path, change) -> None:
    run = _source_run(tmp_path)
    index_before = (run / "source_documents" / "index.json").read_bytes()
    sources_before = (run / "sources.json").read_bytes()
    manifest_before = (run / "run.json").read_bytes()
    review = _review(run)
    change(review)

    with pytest.raises((ValueError, ArtifactConflictError)):
        _apply_reviews(run.name, tmp_path, [review])

    assert (run / "source_documents" / "index.json").read_bytes() == index_before
    assert (run / "sources.json").read_bytes() == sources_before
    assert (run / "run.json").read_bytes() == manifest_before


def test_old_review_is_rejected_after_normalized_capture_changes(tmp_path: Path) -> None:
    run = _source_run(tmp_path)
    review = _review(run)
    (run / "source_documents" / "src_001.md").write_text(
        "Source 1\nPublished: June 17, 2026\nChanged body.", encoding="utf-8"
    )

    with pytest.raises(ArtifactConflictError):
        _apply_reviews(run.name, tmp_path, [review])

    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["source_documents/index.json"]["status"] == "stale"


def test_mutated_review_model_is_revalidated_before_index_write(tmp_path: Path) -> None:
    run = _source_run(tmp_path)
    review = PublicationDateReviewV1.model_validate(_review(run))
    review.reviewed_at = "2026-09-24T14:00:00"
    index_before = (run / "source_documents" / "index.json").read_bytes()
    manifest_before = (run / "run.json").read_bytes()

    with pytest.raises(ValueError):
        _apply_reviews(run.name, tmp_path, [review])

    assert (run / "source_documents" / "index.json").read_bytes() == index_before
    assert (run / "run.json").read_bytes() == manifest_before


def test_legacy_index_rows_without_review_metadata_remain_readable(tmp_path: Path) -> None:
    run = _source_run(tmp_path)
    index = json.loads((run / "source_documents" / "index.json").read_text(encoding="utf-8"))
    assert all("publication_date_review" not in row for row in index["documents"])

    _rebuild_sources(run.name, tmp_path)

    sources = json.loads((run / "sources.json").read_text(encoding="utf-8"))
    assert all(row["published_at"] is None for row in sources["sources"])
