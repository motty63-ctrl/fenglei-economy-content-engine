# Project State

## Verified implementation baseline

Approved Checkpoint Authoring Workflow V1 was implemented at commit `75436e1994ffe037f15f6eda706f98408fd3179e` on `main`. This is a historical implementation baseline, not the current HEAD or a self-updating requirement for later documentation commits.

The Fed Case 2 Video MVP is complete on `main` and publicly released as V0.1.0. The GitHub Release includes the verified `final.mp4` asset (SHA-256 `8796c73d62bed1090a9bbf6af268f5b91406b36913954d944953955d157c564d`). The implementation and release are already pushed; any new documentation-only closeout commit remains local until separately authorized for push. The implementation baseline hash above is historical, not the current HEAD.

## Runtime and run storage

The project is a local Python 3.11+ package with a Typer CLI (`fanglei`, also runnable as `python -m fanglei`). Runs are stored under `runs/` unless `--runs-dir` selects another directory. The standard allocator creates date/sequence/slug IDs and skips IDs already present. Each run is an artifact directory with `run.json` recording stage state, artifact ownership, dependency hashes, and run status.

## Native pipeline

The native pipeline is artifact-first:

`ingest → analyze → research → angle/script → visual plan/storyboard → narration/audio → alignment/timeline → renderer preparation/preflight`

Research is divided into search, source fetch, source selection, factcheck, and research synthesis. Content planning creates and selects angles and validates a structured script against verified facts. Visual planning checks sentence coverage and storyboard quality. The artifact registry enforces stage ownership and hashes; changing an upstream artifact marks dependent artifacts stale.

The ordinary artifact dependency graph is `ARTIFACT_GRAPH` in `src/fanglei/artifact_registry.py`. Run status values currently include `created`, `analyzed`, `scripted`, `visual_planned`, `voice_review_pending`, `voice_approved`, `renderer_ready`, and `failed`.

## Approved-checkpoint authoring and import

Approved Checkpoint Authoring Workflow V1 is complete. Its implemented path is:

`formal artifacts → deterministic approved-checkpoint/2.0 draft → pure validation → explicit hash-bound human approval → write-once seal → V2 importer → schema/provenance/fact-coverage/script-coverage gates → promotion`

Authoring validates one explicitly selected source run and its case binding, hashes, and freshness before seal. The sealed V2 checkpoint contains that approval-time provenance; the importer does not require the original source-run directory to remain present. Approval binds the canonical checkpoint body SHA-256, excluding only the top-level approval record. Sealed checkpoints use `cases/<case-id>/approved-checkpoints/<checkpoint-id>.json`; `.checkpoint-staging/` remains importer-only staging, and `runs/` remains formal run storage.

The separate Python API path uses `CheckpointImporter` to stage a checkpoint and `ApprovedCheckpointMaterializer` to convert it into formal artifacts. Promotion to `runs/<run_id>/` is attempted only when schema, provenance, fact-coverage, and script-coverage gates pass. The import profile has its own `IMPORTED_ARTIFACT_GRAPH`; the native graph remains a separate profile. There is no checkpoint-import or authoring command in `src/fanglei/cli.py`.

Import IDs retain external IDs in `id_mapping.json`; the import manifest records checkpoint and importer fingerprints, pinned source hashes, and semantic artifact hashes. Provenance capture is restricted to official HTTPS URLs listed in the checkpoint. A previously pinned URL/content hash is reused; a content change is surfaced as `SOURCE_CONTENT_CHANGED`.

The local end-to-end authoring → approval → seal → import → promotion acceptance path is covered by tests. Fed Case 2 separately has a completed native run and public video MVP, but no new Fed V2 checkpoint or checkpoint-import promotion.

## Fed SEP revisions case

Fed Case 2 identity is locked in `cases/fed-sep-revisions/CASE_STATE.md`. Its native source-inventory run is `2026-09-24-001-fed-sep-case-2-source-inventory`. The four Federal Reserve documents and approved `authoritative_primary_set/1.0` package remain current. Package SHA-256 is `32661017df86af572c91465bd0a1a5a21e9d0028554b8da7bdc061b702ee70eb`; independent source count remains `1`, while legacy `selection_status` remains `insufficient_sources`.

The current native facts artifact is schema `2.2` with 38 claims: 9 verified, 6 conflicted, and 23 unverified. Five core June-to-September 2026 SEP median comparisons are verified with `authoritative_primary_attestation`; September statement claims for economic activity and inflation are also verified. `research_focus.json` and the Research synthesis are current. The Research SHA-256 is `3ee9a0eff9ee168d39d5c9c9bc319a877b5f492868bcb4df10d978d1a2cad89f`. The locked focus distinguishes FOMC participants' SEP projections/assessments from the Committee's public FOMC statement and prohibits unsupported causality, motive, market-impact, or commitment claims.

Content planning and the first video MVP are complete for the new Case 2 run. Five eligible candidates are present in `angles.json`; the user selected `angle_001` (“把已核验记录并排看”). Its evidence-grounded script cites the five verified SEP comparisons and the September statement's verified inflation claim. Human-approved Volcengine narration, a proportional sentence-level timeline, an eight-scene visual plan, and the final MP4 are present. See `docs/FED_CASE_2_DEMO.md` for exact artifact and media details, provenance, verification, and limitations.

The final MP4 is `runs/2026-09-24-001-fed-sep-case-2-source-inventory/final.mp4` (1080×1920, 30 FPS, H.264/AAC, about 74.633 seconds). Caption timing is sentence-level proportional timing, not WhisperX word-level forced alignment. The video is an MVP output; the estimated timing must not be described as measured word timing.

The original Fed approved checkpoint remains blocked by `ANGLE_FORMAL_FIELDS_MISSING`. The missing 12 formal `AngleCandidate` fields were not recovered from approved source material. Do not repair, backfill, infer, default, copy, or upgrade that checkpoint. GDP artifacts and test fixtures are prohibited recovery sources.

V0.1.0 implementation and video release are public on `main`. Only the current documentation-only closeout commit is local and awaits separate push authorization. Read actual Git state for current HEAD and ahead/behind; hashes in documentation record snapshots and are not self-updating HEAD requirements. See `docs/CURRENT_HANDOFF.md` for the handoff boundary.
## Voice, alignment, and renderer boundaries

Production narration is a separate audio-only operation. `generate-voice` supports Azure and Volcengine provider adapters, validates canonical WAV audio and signal quality, writes narration audio/metadata/quality artifacts, and stops at `voice_review_pending`. Human approval is bound to the current audio hash. The CLI's `prepare-renderer` path accepts only fake narration, alignment, and probe providers; its outputs are engineering fixtures, not production speech or measured timings.

Production alignment has programmatic APIs for writing an alignment candidate and a narrowly scoped human-reviewed mismatch promotion path. No alignment command is exposed by the CLI. `timeline.json` and subtitle generation require a valid final `alignment.json`. Renderer preparation builds a Nikola project and runs preflight/QA; the CLI does not expose a final video-render command. Subtitle generation and audio mastering are separate CLI commands and require their declared upstream artifacts and approvals.

## Current schemas

The importer validates formal facts against `docs/v0.2/facts.schema.json` and scripts against `docs/v0.3/script-contract.schema.json`; angle data is validated against the existing `AngleCandidate` model in `src/fanglei/content_models.py`. Required semantic fields are not inferred from an angle title or filled with defaults by the importer.
