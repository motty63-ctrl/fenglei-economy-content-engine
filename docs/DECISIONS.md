# Architecture Decisions

These decisions describe the current contracts visible in code and schemas.

## Artifacts are owned and dependency-tracked

Each artifact has an owner stage, content hash, and input dependency hashes. A changed upstream artifact invalidates descendants so later stages cannot silently reuse stale outputs. This keeps runs inspectable and resumable.

## Checkpoint imports use a separate graph profile

Imported checkpoints enter through `CheckpointImporter` and `ApprovedCheckpointMaterializer`, with an `IMPORTED_ARTIFACT_GRAPH` selected only for imported runs. The ordinary `ARTIFACT_GRAPH` stays independent so import support does not change native pipeline dependencies.

## Identifiers are mapped, not silently replaced

Checkpoint IDs remain visible as source/external IDs, while deterministic canonical IDs satisfy formal artifact contracts. `id_mapping.json` and the import manifest preserve the mapping and its hash for auditability.

Legacy V1 checkpoint fingerprinting retains its historical runtime-field exclusion and existing materialization behavior. V2 approval instead hashes the entire canonical checkpoint body, excluding only the top-level `approval` record; body timestamps and snapshot fields are protected. The V2 importer fingerprint derives from that verified body hash, checkpoint contract version, and importer version. Import-time audit fields remain importer-generated metadata and are not substituted into the approved checkpoint body.

## Approved checkpoint authoring V1 is complete

The supported new-checkpoint path is formal source-run artifacts → deterministic `approved-checkpoint/2.0` draft → pure validation → explicit human approval bound to the canonical body SHA-256 → write-once seal → V2 import → existing schema, provenance, fact-coverage, and script-coverage gates → promotion. The importer remains independent of the source-run directory after sealing; source-run identity, case binding, freshness, and protected hashes are verified before seal and retained as provenance evidence.

V2 does not redefine legacy `1.0` or `approved-checkpoint/1.0`. Existing V1 fingerprint and materialization semantics remain in force. A V1 checkpoint is never silently upgraded, backfilled, or given V2 approval meaning.

## Import conversion preserves approved meaning

The importer performs structural conversion and deterministic metadata derivation. It does not use an LLM to rewrite evidence, claims, angle, or script. Existing facts and script schemas remain authoritative; missing required semantic fields fail closed instead of receiving guessed values or defaults.

## Approved-checkpoint recovery requires identity-bound source material

Recover missing semantic values only from original approved material whose checkpoint identity, case context, and approval provenance bind it to the import being recovered. A complete artifact from another case or a test fixture is not a substitute. Do not infer, regenerate, default, or copy missing values; if the original approved material cannot be located with sufficient provenance, keep the import blocked.

## Fed Case 2 uses a new V2 checkpoint

The original Fed approved checkpoint remains blocked by `ANGLE_FORMAL_FIELDS_MISSING`. Its 12 missing `AngleCandidate` values have not been recovered from original approved material; do not repair, backfill, infer, default, copy, or upgrade that checkpoint to V2. GDP artifacts and test fixtures are not recovery sources.

The next Fed Case 2 path is to create a separate, complete `approved-checkpoint/2.0` checkpoint. Begin with a read-only inventory for an existing complete formal source run; if none exists, decide which native pipeline stage to resume. Until then, no new Fed V2 checkpoint, promotion, or production run exists.

## Provenance is limited to the checkpoint's source allowlist

Only official HTTPS URLs explicitly listed by the checkpoint may be captured. A successful URL/content hash is pinned and reused. Changed content is surfaced instead of silently replacing the approved evidence basis.

## Staging precedes production promotion

Checkpoint conversion first writes an isolated staging package. Schema, provenance, fact-coverage, and script-coverage gates must all pass before the importer allocates and atomically publishes a production run. Failed imports remain out of `runs/`.

## Production voice stops for human review

Real TTS creates canonical audio and quality artifacts, then sets `voice_review_pending`. A human approval is bound to the exact audio hash; regenerating audio invalidates earlier downstream review state. Fake narration and alignment remain engineering/test inputs.

## Alignment and media outputs require measured inputs

Production alignment validates the approved audio hash, duration, sentence coverage, ordering, boundaries, and model provenance. Timeline/subtitle consumers require final alignment artifacts. Renderer preflight results do not themselves represent a completed video render.
