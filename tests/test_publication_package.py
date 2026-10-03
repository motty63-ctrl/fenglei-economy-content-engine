"""Publication preparation removes review overlays, never accepted history."""
import json

import pytest

from fanglei.artifact_registry import _directory_hash
from fanglei.artifacts import sha256_bytes
from fanglei.errors import ArtifactConflictError
from test_final_render import source_run, _snapshot
from test_qa_implementation_identity import ready_history

OVERLAYS = '<div class="preview-label">PREVIEW · NOT FINAL</div><div id="review-required">HUMAN REVIEW REQUIRED</div>'
SCENES = '<section id="scene_001" data-source-ids="source">Source footer</section>'
SUBTITLES = '<div id="subtitle-layer"><span id="subtitle-text"></span></div>'


@pytest.fixture
def approved_run(source_run):
    from fanglei.final_render import _registry
    package = source_run / "renderer_project_candidate_3"
    html = '<html><body>' + SCENES + OVERLAYS + SUBTITLES + '<script>{"motion":[],"duration_ms":1000}</script></body></html>'
    (package / "review-preview.html").write_text(html, encoding="utf-8", newline="\n")
    reg = _registry(source_run, 3)
    name = "renderer_project_candidate_3"
    reg.manifest.artifacts[name].content_hash = _directory_hash(package)
    for state in reg.manifest.artifacts.values():
        if name in state.dependencies:
            state.dependencies[name] = reg.manifest.artifacts[name].content_hash
    reg.save_manifest()
    ready_history(source_run, approved=True)
    return source_run


def prepare(root):
    from fanglei.publication_package import prepare_publication_renderer_package
    return prepare_publication_renderer_package(root, presentation_mode="publication",
        expected_candidate_sha256=sha256_bytes((root / "final_video_candidate.json").read_bytes()),
        expected_approval_sha256=sha256_bytes((root / "human_final_video_review.json").read_bytes()))


def test_composition_default_review_and_only_overlay_difference():
    from fanglei.preview_composition import review_composition_html
    layout = {"canvas_width":1080, "canvas_height":1920, "reserved_zone":{"width":1000},
              "vertical_padding_px":12, "horizontal_padding_px":12, "line_height":1.2}
    data = {"duration_ms":1000, "scenes":[], "subtitles":[], "motion":"unchanged"}
    default = review_composition_html([SCENES], data, layout, "synthetic")
    review = review_composition_html([SCENES], data, layout, "synthetic", presentation_mode="review")
    publication = review_composition_html([SCENES], data, layout, "synthetic", presentation_mode="publication")
    assert default == review
    assert OVERLAYS in review
    assert publication == review.replace(OVERLAYS, "")
    assert SCENES in publication and SUBTITLES in publication


@pytest.mark.parametrize("mode", ["public", "", None])
def test_unknown_presentation_mode_fails_closed(mode):
    from fanglei.preview_composition import apply_presentation_mode
    with pytest.raises(ValueError, match="PRESENTATION_MODE"):
        apply_presentation_mode(SCENES + OVERLAYS, mode)


@pytest.mark.parametrize("html", [SCENES, OVERLAYS + OVERLAYS, '<div class="preview-label">CHANGED</div>'])
def test_unknown_overlay_structure_is_not_silently_repaired(html):
    from fanglei.preview_composition import apply_presentation_mode
    with pytest.raises(ValueError, match="REVIEW_OVERLAY"):
        apply_presentation_mode(html, "publication")


def test_publication_owner_preserves_all_accepted_inputs(approved_run):
    from fanglei.publication_package import validate_publication_renderer_package
    from fanglei.final_render import _registry
    before = _snapshot(approved_run)
    path = prepare(approved_run)
    manifest = validate_publication_renderer_package(approved_run)
    assert path.name == "publication_renderer_package.json"
    assert manifest.schema_version == "publication-renderer-package/1.0"
    assert manifest.status == "ready_for_publication_render"
    assert manifest.presentation_mode == "publication"
    assert manifest.qa_implementation_status == "superseded"
    assert manifest.accepted_qa.sha256 == manifest.human_final_approval_qa_sha256
    assert manifest.render_configuration.duration_ms == 1000
    source = approved_run / "renderer_project_final"
    output = approved_run / "renderer_project_publication"
    for p in source.rglob("*"):
        if p.is_file():
            relative = p.relative_to(source)
            expected = p.read_bytes()
            if relative.as_posix() == "review-preview.html":
                expected = expected.replace(OVERLAYS.encode("utf-8"), b"")
            assert (output / relative).read_bytes() == expected
    for name, value in before.items():
        if name != "run.json":
            assert (approved_run / name).read_bytes() == value
    reg = _registry(approved_run)
    reg.validate("publication_renderer_package.json")
    reg.validate("human_final_video_review.json")
    assert not (approved_run / "publication.mp4").exists()
    with pytest.raises(ArtifactConflictError, match="ALREADY_EXISTS"):
        prepare(approved_run)


@pytest.mark.parametrize("name", ["final.mp4", "final_video_candidate.json", "human_final_video_review.json", "timeline_candidate_2.json", "renderer_project_final/review-preview.html", "audio/narration.wav", "subtitle_track.json"])
def test_upstream_changes_block_publication_currentness(approved_run, name):
    from fanglei.publication_package import validate_publication_renderer_package
    prepare(approved_run)
    p = approved_run / name
    p.write_bytes(p.read_bytes() + b"changed")
    before = _snapshot(approved_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_publication_renderer_package(approved_run)
    assert _snapshot(approved_run) == before


def test_publication_changes_do_not_stale_final_history(approved_run):
    from fanglei.final_render import _registry
    from fanglei.final_video_qa import validate_existing_human_final_video_approval
    from fanglei.publication_package import validate_publication_renderer_package
    prepare(approved_run)
    p = approved_run / "renderer_project_publication/review-preview.html"
    p.write_bytes(p.read_bytes() + b"changed")
    with pytest.raises(ArtifactConflictError):
        validate_publication_renderer_package(approved_run)
    reg = _registry(approved_run)
    for name in ("final.mp4", "final_video_candidate.json", "final_video_qa.json", "human_final_video_review.json"):
        reg.validate(name)
    assert validate_existing_human_final_video_approval(approved_run).decision == "approved"


def test_publication_graph_is_acyclic_without_reverse_final_dependencies(approved_run):
    from fanglei.final_render import _registry
    prepare(approved_run)
    graph = _registry(approved_run).graph
    done = set()
    def visit(name, trail):
        assert name not in trail
        if name in done:
            return
        for dep in graph[name][1]:
            visit(dep, trail | {name})
        done.add(name)
    for name in graph:
        visit(name, set())
    for name in ("final.mp4", "final_video_candidate.json", "final_video_qa.json", "human_final_video_review.json"):
        assert not any("publication" in dep for dep in graph[name][1])


def test_wrong_expected_approval_hash_writes_nothing(approved_run):
    from fanglei.publication_package import prepare_publication_renderer_package
    before = _snapshot(approved_run)
    with pytest.raises(ValueError, match="EXPECTED_HASH"):
        prepare_publication_renderer_package(approved_run, presentation_mode="publication",
            expected_candidate_sha256=sha256_bytes((approved_run / "final_video_candidate.json").read_bytes()),
            expected_approval_sha256="0" * 64)
    assert _snapshot(approved_run) == before


@pytest.mark.parametrize("changed", ["review-preview.html", "data/timeline.json", "package.json"])
def test_hash_current_but_unauthorized_publication_copy_is_rejected(approved_run, changed):
    from fanglei.final_render import _registry
    from fanglei.publication_package import validate_publication_renderer_package
    prepare(approved_run)
    reg = _registry(approved_run)
    package = approved_run / "renderer_project_publication"
    files = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    files[changed] += b"unauthorized content change"
    reg.write_directory("renderer_project_publication", files, "publication_package", force=True)
    manifest = json.loads((approved_run / "publication_renderer_package.json").read_text())
    manifest["renderer_package"]["sha256"] = reg.manifest.artifacts["renderer_project_publication"].content_hash
    reg.write_json("publication_renderer_package.json", manifest, "publication_package", force=True)
    reg.save_manifest()
    reg.validate("publication_renderer_package.json")
    with pytest.raises(ValueError, match="UNAUTHORIZED_DIFFERENCE"):
        validate_publication_renderer_package(approved_run)


def test_publication_requires_existing_human_approval(source_run):
    from fanglei.publication_package import prepare_publication_renderer_package
    ready_history(source_run, approved=False)
    before = _snapshot(source_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        prepare_publication_renderer_package(source_run, presentation_mode="publication",
            expected_candidate_sha256=sha256_bytes((source_run / "final_video_candidate.json").read_bytes()),
            expected_approval_sha256="0" * 64)
    assert _snapshot(source_run) == before
