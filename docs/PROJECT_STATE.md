# Project State

## Verified implementation baseline

Approved Checkpoint Authoring Workflow V1 is implemented at commit `75436e1994ffe037f15f6eda706f98408fd3179e` on `main`. At the start of this documentation closeout, local `main`, `origin/main`, and GitHub `main` pointed to that commit and the working tree was clean. This hash records the implementation baseline; it is not a self-updating requirement for later documentation commits.

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

The local end-to-end authoring → approval → seal → import → promotion acceptance path is covered by tests. It does not mean that the Fed SEP case has a new V2 checkpoint or production run.

## Fed SEP revisions case

Fed Case 2 identity is locked in `cases/fed-sep-revisions/CASE_STATE.md`. Its native source-inventory run is `2026-09-24-001-fed-sep-case-2-source-inventory`. The four Federal Reserve documents and approved `authoritative_primary_set/1.0` package remain current. Package SHA-256 is `32661017df86af572c91465bd0a1a5a21e9d0028554b8da7bdc061b702ee70eb`; independent source count remains `1`, while legacy `selection_status` remains `insufficient_sources`.

The current native facts artifact is schema `2.2` with 38 claims: 9 verified, 6 conflicted, and 23 unverified. Five core June-to-September 2026 SEP median comparisons are verified with `authoritative_primary_attestation`; September statement claims for economic activity and inflation are also verified. `research_focus.json` and the Research synthesis are current. The Research SHA-256 is `3ee9a0eff9ee168d39d5c9c9bc319a877b5f492868bcb4df10d978d1a2cad89f`. The locked focus distinguishes FOMC participants' SEP projections/assessments from the Committee's public FOMC statement and prohibits unsupported causality, motive, market-impact, or commitment claims.

No valid `angles.json`, selected angle, script, or video artifact exists. Exact next step: implement and verify the generic deterministic offline angle planner, then generate `angles.json` through the formal angle-generation owner and stop for human selection. No live provider or TTS is authorized for this step.

The original Fed approved checkpoint remains blocked by `ANGLE_FORMAL_FIELDS_MISSING`. The missing 12 formal `AngleCandidate` fields were not recovered from approved source material. Do not repair, backfill, infer, default, copy, or upgrade that checkpoint. GDP artifacts and test fixtures are prohibited recovery sources.

The implementation remains on local branch `overnight/fed-sep-evidence-2026-09-24`, based on remote `main @ 4ec89bc6b59a128d24a75ca4fdcc776e3fe25f91`; it has not been pushed. The branch baseline and current HEAD are separate facts: use actual Git state for current HEAD. See `docs/CURRENT_HANDOFF.md` for the current continuation boundary.
## Voice, alignment, and renderer boundaries

Production narration is a separate audio-only operation. `generate-voice` supports Azure and Volcengine provider adapters, validates canonical WAV audio and signal quality, writes narration audio/metadata/quality artifacts, and stops at `voice_review_pending`. Human approval is bound to the current audio hash. The CLI's `prepare-renderer` path accepts only fake narration, alignment, and probe providers; its outputs are engineering fixtures, not production speech or measured timings.

Production alignment has programmatic APIs for writing an alignment candidate and a narrowly scoped human-reviewed mismatch promotion path. No alignment command is exposed by the CLI. `timeline.json` and subtitle generation require a valid final `alignment.json`. Renderer preparation builds a Nikola project and runs preflight/QA; the CLI does not expose a final video-render command. Subtitle generation and audio mastering are separate CLI commands and require their declared upstream artifacts and approvals.

## Current schemas

The importer validates formal facts against `docs/v0.2/facts.schema.json` and scripts against `docs/v0.3/script-contract.schema.json`; angle data is validated against the existing `AngleCandidate` model in `src/fanglei/content_models.py`. Required semantic fields are not inferred from an angle title or filled with defaults by the importer.
