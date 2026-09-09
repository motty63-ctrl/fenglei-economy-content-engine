from pathlib import Path

import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest


def test_upstream_change_marks_all_descendants_stale(tmp_path: Path) -> None:
    manifest = RunManifest(run_id="run", created_at="now", updated_at="now")
    registry = ArtifactRegistry(tmp_path, manifest)
    registry.write_text("source.md", "one", "ingest")
    registry.write_json("questions.json", {"q": 1}, "analyze")
    registry.write_json("search_results.json", {"results": []}, "search")
    registry.write_json("source_documents/index.json", {"documents": []}, "source_fetch")
    registry.write_json("sources.json", {"sources": []}, "source_selection")
    registry.write_json("facts.json", {"claims": []}, "factcheck")
    registry.write_text("research.md", "brief", "research_synthesis")

    registry.write_text("source.md", "two", "ingest", force=True)

    assert manifest.artifacts["source.md"].status == "valid"
    for name in (
        "questions.json",
        "search_results.json",
        "source_documents/index.json",
        "sources.json",
        "facts.json",
        "research.md",
    ):
        assert manifest.artifacts[name].status == "stale"


def test_only_owner_can_write_and_stale_cannot_be_read(tmp_path: Path) -> None:
    manifest = RunManifest(run_id="run", created_at="now", updated_at="now")
    registry = ArtifactRegistry(tmp_path, manifest)
    with pytest.raises(ArtifactConflictError, match="owner"):
        registry.write_text("source.md", "x", "search")

    registry.write_text("source.md", "one", "ingest")
    registry.write_json("questions.json", {"q": 1}, "analyze")
    registry.write_text("source.md", "two", "ingest", force=True)
    with pytest.raises(ArtifactConflictError, match="stale"):
        registry.read_json("questions.json")


def test_on_disk_upstream_tamper_propagates_stale(tmp_path: Path) -> None:
    manifest = RunManifest(run_id="run", created_at="now", updated_at="now")
    registry = ArtifactRegistry(tmp_path, manifest)
    registry.write_text("source.md", "one", "ingest")
    registry.write_json("questions.json", {"q": 1}, "analyze")
    registry.write_json("search_results.json", {"results": []}, "search")
    (tmp_path / "source.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(ArtifactConflictError, match="stale"):
        registry.validate("search_results.json")
    assert manifest.artifacts["source.md"].status == "stale"
    assert manifest.artifacts["questions.json"].status == "stale"
    assert manifest.artifacts["search_results.json"].status == "stale"


def test_source_raw_asset_tamper_stales_index_and_descendants(tmp_path: Path) -> None:
    from fanglei.artifacts import sha256_text

    manifest = RunManifest(run_id="run", created_at="now", updated_at="now")
    registry = ArtifactRegistry(tmp_path, manifest)
    registry.write_text("source.md", "one", "ingest")
    registry.write_json("questions.json", {"q": 1}, "analyze")
    registry.write_json("search_results.json", {"results": []}, "search")
    normalized = tmp_path / "source_documents" / "src_001.md"
    raw = tmp_path / "source_documents" / "raw" / "src_001.pdf"
    normalized.parent.mkdir(parents=True)
    raw.parent.mkdir(parents=True)
    normalized.write_text("GDP 2.8%", encoding="utf-8")
    raw.write_text("original-pdf", encoding="utf-8")
    registry.write_json("source_documents/index.json", {"documents": [{
        "source_id": "src_001",
        "path": "source_documents/src_001.md",
        "content_hash": sha256_text("GDP 2.8%"),
        "files": [
            {"role": "normalized_text", "path": "source_documents/src_001.md", "content_hash": sha256_text("GDP 2.8%")},
            {"role": "raw_response", "path": "source_documents/raw/src_001.pdf", "content_hash": sha256_text("original-pdf")},
        ],
    }]}, "source_fetch")
    registry.write_json("sources.json", {"sources": []}, "source_selection")
    registry.write_json("facts.json", {"claims": []}, "factcheck")

    raw.write_text("tampered", encoding="utf-8")
    with pytest.raises(ArtifactConflictError, match="source document"):
        registry.validate("facts.json")
    assert manifest.artifacts["source_documents/index.json"].status == "stale"
    assert manifest.artifacts["facts.json"].status == "stale"
