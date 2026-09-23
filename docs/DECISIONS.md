# Architecture Decisions

These decisions describe the current contracts visible in code and schemas.

## Artifacts are owned and dependency-tracked

Each artifact has an owner stage, content hash, and input dependency hashes. A changed upstream artifact invalidates descendants so later stages cannot silently reuse stale outputs. This keeps runs inspectable and resumable.

## Checkpoint imports use a separate graph profile

Imported checkpoints enter through `CheckpointImporter` and `ApprovedCheckpointMaterializer`, with an `IMPORTED_ARTIFACT_GRAPH` selected only for imported runs. The ordinary `ARTIFACT_GRAPH` stays independent so import support does not change native pipeline dependencies.

## Identifiers are mapped, not silently replaced

Checkpoint IDs remain visible as source/external IDs, while deterministic canonical IDs satisfy formal artifact contracts. `id_mapping.json` and the import manifest preserve the mapping and its hash for auditability.

Runtime timestamps are audit metadata only. They are excluded from checkpoint fingerprinting, deterministic ID assignment, mapping hashes, and semantic artifact hashes so repeat imports of the same checkpoint remain stable.

## Import conversion preserves approved meaning

The importer performs structural conversion and deterministic metadata derivation. It does not use an LLM to rewrite evidence, claims, angle, or script. Existing facts and script schemas remain authoritative; missing required semantic fields fail closed instead of receiving guessed values or defaults.

## Provenance is limited to the checkpoint's source allowlist

Only official HTTPS URLs explicitly listed by the checkpoint may be captured. A successful URL/content hash is pinned and reused. Changed content is surfaced instead of silently replacing the approved evidence basis.

## Staging precedes production promotion

Checkpoint conversion first writes an isolated staging package. Schema, provenance, fact-coverage, and script-coverage gates must all pass before the importer allocates and atomically publishes a production run. Failed imports remain out of `runs/`.

## Production voice stops for human review

Real TTS creates canonical audio and quality artifacts, then sets `voice_review_pending`. A human approval is bound to the exact audio hash; regenerating audio invalidates earlier downstream review state. Fake narration and alignment remain engineering/test inputs.

## Alignment and media outputs require measured inputs

Production alignment validates the approved audio hash, duration, sentence coverage, ordering, boundaries, and model provenance. Timeline/subtitle consumers require final alignment artifacts. Renderer preflight results do not themselves represent a completed video render.
