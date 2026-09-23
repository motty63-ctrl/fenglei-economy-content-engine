# Project State

## Runtime and run storage

The project is a local Python 3.11+ package with a Typer CLI (`fanglei`, also runnable as `python -m fanglei`). Runs are stored under `runs/` unless `--runs-dir` selects another directory. The standard allocator creates date/sequence/slug IDs and skips IDs already present. Each run is an artifact directory with `run.json` recording stage state, artifact ownership, dependency hashes, and run status.

## Native pipeline

The native pipeline is artifact-first:

`ingest → analyze → research → angle/script → visual plan/storyboard → narration/audio → alignment/timeline → renderer preparation/preflight`

Research is divided into search, source fetch, source selection, factcheck, and research synthesis. Content planning creates and selects angles and validates a structured script against verified facts. Visual planning checks sentence coverage and storyboard quality. The artifact registry enforces stage ownership and hashes; changing an upstream artifact marks dependent artifacts stale.

The ordinary artifact dependency graph is `ARTIFACT_GRAPH` in `src/fanglei/artifact_registry.py`. Run status values currently include `created`, `analyzed`, `scripted`, `visual_planned`, `voice_review_pending`, `voice_approved`, `renderer_ready`, and `failed`.

## Approved-checkpoint import

The code has a separate Python API path: `CheckpointImporter` stages an approved checkpoint, and `ApprovedCheckpointMaterializer` converts its structure into formal artifacts. Staging is under `.checkpoint-staging/`; promotion to `runs/<run_id>/` is attempted only when schema, provenance, fact-coverage, and script-coverage gates pass. The import profile has its own `IMPORTED_ARTIFACT_GRAPH`; the native graph remains a separate profile. There is no checkpoint-import command in `src/fanglei/cli.py`.

Import IDs retain external IDs in `id_mapping.json`; the import manifest records checkpoint and importer fingerprints, pinned source hashes, and semantic artifact hashes. Provenance capture is restricted to official HTTPS URLs listed in the checkpoint. A previously pinned URL/content hash is reused; a content change is surfaced as `SOURCE_CONTENT_CHANGED`.

## Voice, alignment, and renderer boundaries

Production narration is a separate audio-only operation. `generate-voice` supports Azure and Volcengine provider adapters, validates canonical WAV audio and signal quality, writes narration audio/metadata/quality artifacts, and stops at `voice_review_pending`. Human approval is bound to the current audio hash. The CLI's `prepare-renderer` path accepts only fake narration, alignment, and probe providers; its outputs are engineering fixtures, not production speech or measured timings.

Production alignment has programmatic APIs for writing an alignment candidate and a narrowly scoped human-reviewed mismatch promotion path. No alignment command is exposed by the CLI. `timeline.json` and subtitle generation require a valid final `alignment.json`. Renderer preparation builds a Nikola project and runs preflight/QA; the CLI does not expose a final video-render command. Subtitle generation and audio mastering are separate CLI commands and require their declared upstream artifacts and approvals.

## Current schemas

The importer validates formal facts against `docs/v0.2/facts.schema.json` and scripts against `docs/v0.3/script-contract.schema.json`; angle data is validated against the existing `AngleCandidate` model in `src/fanglei/content_models.py`. Required semantic fields are not inferred from an angle title or filled with defaults by the importer.
