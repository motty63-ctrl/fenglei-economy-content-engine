# Approved Checkpoint Authoring Workflow V1

**Status:** Design specification; implementation has not started.
**Checkpoint contract:** `approved-checkpoint/2.0`
**Scope:** Deterministically package existing formal run artifacts, validate them, record an explicit human approval bound to the checkpoint body, seal the checkpoint in tracked case storage, then hand it to the existing importer.

## 1. Goals / non-goals

V1 provides a fail-closed path from one native formal run to one immutable, reviewable, provenance-bound checkpoint. It must:

- assemble checkpoint content only from current formal artifacts belonging to one source run and one case;
- preserve angle, claim, evidence, research, and script semantic text exactly;
- validate the complete V2 contract before approval and again at import;
- bind human approval to the SHA-256 of the canonical checkpoint body;
- bind each source to the extracted-text and indexed-file hashes recorded in `source_documents/index.json`;
- persist sealed checkpoints under the case tree using write-once semantics; and
- retain the existing importer gates and promotion boundary.

### Non-goals

V1 does not:

- repair or resume the blocked legacy Fed SEP checkpoint;
- generate, infer, default, score, or copy missing semantic angle fields;
- call an LLM or regenerate content;
- automatically approve a checkpoint;
- change the `AngleCandidate` contract;
- relax importer gates or source provenance checks;
- change content generation, TTS, alignment, narration, or renderer behavior;
- add a GUI or remote approval service; or
- change the meaning of `1.0` or `approved-checkpoint/1.0`.

GDP artifacts and test fixtures are not production inputs to a checkpoint and are never a recovery source for Fed values.

## 2. Existing components to reuse

| Existing component | V1 use |
|---|---|
| `AngleCandidate` in `src/fanglei/content_models.py` | Validate the selected full candidate without changing its fields. |
| `score_angles`, `select_angle` in `src/fanglei/angle_policy.py` | Existing content-time scoring/selection only. Authoring reads the recorded selected candidate; it does not rerun selection. |
| `angles.json`, `angle.md`, `script.json`, `script.md` from `src/fanglei/content_pipeline.py` | Source records for selected angle and structured script. |
| `facts.json`, `sources.json`, `source_documents/index.json`, `research.md` from `src/fanglei/pipeline.py` | Source records for claims, evidence, allowlisted source identities, snapshots, and research. |
| `docs/v0.2/facts.schema.json`, `docs/v0.3/script-contract.schema.json` | Validate the formal facts and structured script outputs produced by import. |
| `ArtifactRegistry` and `ARTIFACT_GRAPH` in `src/fanglei/artifact_registry.py` | Require current source artifacts, verify recorded file/dependency hashes, and provide upstream hash values. |
| `CheckpointImporter` and `ApprovedCheckpointMaterializer` in `src/fanglei/checkpoint_import.py` | Keep as the final conversion, provenance, coverage, staging, and promotion boundary; add V2 verification without weakening existing gates. |
| `sha256_text`, `sha256_bytes`, atomic file helpers in `src/fanglei/artifacts.py` | Reuse byte hashing and safe writing where compatible. Sealed publication must add no-overwrite behavior; `atomic_write_json` alone replaces existing files. |
| `approve_voice` / `validate_voice_approval` and `promote_alignment` | Pattern references for explicit, hash-bound human review. Their models and scope are not reused as checkpoint approval. |

The current repository has no checkpoint builder/exporter, V2 input model/schema, generic approval record, authoring API, or checkpoint authoring CLI.

## 3. V2 checkpoint envelope

The approved serialized file is one JSON object. The approval record is a sibling of the canonical body, not part of it.

```json
{
  "checkpoint_schema_version": "approved-checkpoint/2.0",
  "checkpoint_id": "<stable-id>",
  "case_id": "<case-id>",
  "source_run_id": "<run-id>",
  "protected_artifact_hashes": {
    "checkpoint_authoring_binding.json": "<sha256>",
    "source.md": "<sha256>",
    "questions.json": "<sha256>",
    "source_documents/index.json": "<sha256>",
    "sources.json": "<sha256>",
    "facts.json": "<sha256>",
    "research.md": "<sha256>",
    "angles.json": "<sha256>",
    "angle.md": "<sha256>",
    "script.json": "<sha256>",
    "script.md": "<sha256>"
  },
  "facts_source": {
    "schema_version": "2.1",
    "policy_version": "<native-policy-version>",
    "summary": {}
  },
  "research": { "content": "<exact research.md text>" },
  "sources": [
    {
      "external_id": "<native source_id>",
      "url": "<exact allowlisted HTTPS URL>",
      "official": true,
      "official_review": {
        "decision": "approved_official",
        "reviewer": "<reviewer>",
        "reviewed_at": "<timezone-aware ISO-8601 timestamp>",
        "basis": "<explicit review basis>"
      },
      "title": "<exact source title>",
      "published_at": "<source value or null>",
      "snapshot": {
        "source_text_sha256": "<documents[].content_hash>",
        "raw_capture_bytes_sha256": "<matching raw PDF asset hash, otherwise null>",
        "indexed_file_hashes": [
          { "role": "normalized_text", "path": "<indexed relative path>", "hash_kind": "utf8_text_sha256", "sha256": "<indexed file content_hash>" }
        ]
      }
    }
  ],
  "claims": [],
  "evidence": [],
  "angle": {},
  "script": {},
  "approval": {
    "status": "approved",
    "reviewer": "<reviewer>",
    "approved_at": "<timezone-aware ISO-8601 timestamp>",
    "body_sha256": "<64 lowercase hexadecimal characters>"
  }
}
```

Required fields and types are strict for V2. Unknown V2 envelope or row fields are rejected unless explicitly added in a later version. The body must contain exactly the fields shown above other than `approval`; row details for `claims`, `evidence`, `angle`, and `script` are defined in Sections 7–8. `facts_source.summary` preserves the native summary object as-is. Optional source dates may be `null`; other required strings must be non-empty. IDs are opaque non-empty strings except where an existing formal schema imposes a stricter pattern.

`source_run_id` is the immutable provenance identity of the source run; it is not a requirement that the run remain available at import time. `case_id` must match the explicit, registered `checkpoint_authoring_binding.json` artifact in that run. Current `RunManifest`/`InputInfo` has no case field; Section 13 defines the single binding contract. It must not derive `case_id` from a run slug, title, source text, or directory name.

## 4. Canonical body and hash boundary

Let `body` be the entire V2 envelope with the top-level `approval` property removed. No other property is omitted from the body hash.

Canonicalization is UTF-8 JSON with:

```python
json.dumps(body, ensure_ascii=False, sort_keys=True,
           separators=(",", ":"), allow_nan=False).encode("utf-8")
```

`body_sha256` is lowercase hexadecimal SHA-256 of those exact bytes. Object key order and whitespace do not affect the hash; array order, exact strings, Unicode code points, nulls, booleans, IDs, timestamps inside the body, source snapshot hashes, and protected artifact hashes do. No trimming, Unicode normalization, case folding, runtime-field deletion, or semantic normalization is permitted before hashing.

The approval record is excluded in full to avoid self-reference. In particular, `approved_at` and `reviewer` live only in `approval`; changing them does not change the body hash. The sealed file's full bytes remain subject to Git history and normal file integrity checks. V1 does not claim a cryptographic signature or authenticate a reviewer's identity.

`approval.body_sha256` is the only V2 checkpoint-body digest name. `checkpoint_content_sha256` is not an envelope field or an alias: it remains an importer-generated field in staging `checkpoint_fingerprint.json`, the ID-mapping metadata, and the imported `import_manifest.json`, where it records the importer fingerprint input. For V2, its value is the canonical body SHA-256 after successful V2 verification. The import fingerprint remains versioned by checkpoint schema and importer version; V2 must not use the V1 `_without_runtime` rules to calculate the approval body hash. Legacy fingerprint behavior remains unchanged.

## 5. State transitions

| State | Representation | Allowed transition / gate |
|---|---|---|
| `draft` | In-memory body assembled from one source run; no approval record | `build_draft` succeeds only if required source artifacts are present, current, and identity-consistent. |
| `validated` | Draft plus validation report and canonical `body_sha256`; no approval | Every V2 structural, identity, artifact hash, source review, snapshot, facts, angle, and script check passes. Any failure leaves it a draft. |
| `approved` | In-memory approval record bound to the validated body hash | Explicit human call supplies reviewer and the exact displayed hash. No automatic approval path. |
| `sealed` | Write-once JSON at `cases/<case-id>/approved-checkpoints/<checkpoint-id>.json` | Before publication, revalidate the explicit source-run binding, source-run identity, artifact freshness, and all protected artifact hashes; recompute and compare body hash; publication must refuse replacement. |
| `imported` | Existing importer reports `promoted`; imported run and manifest exist under `runs/` | Importer independently verifies V2 approval/body hash, checkpoint-internal identities and references, source snapshots/captures, schemas, provenance, fact coverage, and script coverage. It does not open the source run. |

`CheckpointImporter.stage()` is not a pre-approval validator: it requires `status=approved`, writes `.checkpoint-staging/`, and may capture URLs. Draft validation must be pure and must not call it. A failed import leaves the sealed checkpoint unchanged and not `imported`.

If any protected input changes before sealing, the draft must be rebuilt and revalidated. If the body changes after approval, the approval is rejected and the flow returns to `draft`. A new body requires a new explicit review and approval. Once sealed, subsequent source-run artifact changes or deletion do not affect import; the old checkpoint remains immutable and import validates only its approved body, internal references, and independently recaptured source snapshots.

## 6. Input artifact requirements

The authoring API requires these exact source-run artifacts and validates each with `ArtifactRegistry` before reading:

- `run.json` with matching `run_id` and current artifact states;
- `checkpoint_authoring_binding.json`, registered in `ARTIFACT_GRAPH`, with matching `run_id` and explicit `case_id`;
- `source.md`, `questions.json`, `facts.json`, `research.md`, `sources.json`;
- `source_documents/index.json` and each indexed source document/file whose recorded hash is present;
- `angles.json`, `angle.md`, `script.json`, and `script.md`.

All listed artifacts must be valid, have matching recorded content hashes and dependency hashes, and belong to the same source run. `run.json` is read as the artifact manifest; it is not itself a registry artifact hash. `protected_artifact_hashes` contains the binding artifact and every required registered source artifact, using their exact registry content hashes. Individual indexed source documents/files are represented in `sources[].snapshot.indexed_file_hashes`, not duplicated in that map. Indexed source documents and files must exist and match the index. No fallback to fixtures, another run, cached unrelated captures, or other cases is allowed. Source snapshot fields are copied from the verified index as specified in Sections 7 and 10. These checks happen during authoring, validation, and again immediately before seal; they are not deferred to import.

`script.json` has no `run_id`; its same-run identity is established by resolving it only from the source run directory and requiring its recorded `angle_id` to match that run's selected angle. `angles.json.run_id` and `facts.json.run_id`, where present, must equal the source run ID.

## 7. Exact artifact-to-checkpoint field mappings

### Identity and protected hashes

- `checkpoint_id`: explicit stable authoring input; never derived from body text. It is immutable after sealing.
- `case_id`: explicit source-run case binding.
- `source_run_id`: exact ID recorded in the source run manifest; retained as provenance identity, not a requirement that its directory exist at import.
- `protected_artifact_hashes`: registry hashes of every artifact in Section 6, by repository-relative artifact name.

### Research

- `research.content` is the exact UTF-8 text of `research.md`, including its line endings as read and final newline if present. It is not summarized or regenerated.

### Sources and source snapshots

- `sources[].external_id` ← `sources.json.sources[].source_id`.
- `url`, `title`, and `published_at` ← exact corresponding `sources.json` values.
- `official` and `official_review` ← explicit per-source review metadata; never inferred from `source_type`, `credibility_tier`, host name, URL shape, or evidence.
- `snapshot.source_text_sha256` ← matching `source_documents/index.json.documents[].content_hash`, defined as SHA-256 of the exact UTF-8 encoding of the extracted `doc.text` string written to the normalized document path.
- `snapshot.raw_capture_bytes_sha256` ← the `content_hash` of the matching `files[]` entry with `role: "raw_response"` only when it identifies the persisted original PDF bytes; otherwise `null`. Do not treat `document_hash` as a uniform raw-byte digest.
- `snapshot.indexed_file_hashes` ← every `documents[].files[]` entry in original order, preserving `role` and relative `path`, copying `content_hash` into `sha256`, and assigning `hash_kind` by the actual persisted representation: `normalized_text` and JSON `raw_response` are `utf8_text_sha256`; PDF `raw_response` and `page_index` are `file_bytes_sha256`.
- The selected source row and document-index row must agree on `source_id`, URL/original URL, and case/run context. Missing or contradictory values fail.

### Angle

1. Read `selected_angle_id` from `angle.md`.
2. Find exactly one candidate in `angles.json.candidates` with that `angle_id`.
3. Require that candidate to be an `AngleCandidate`, have `eligibility == "eligible"`, and have all formal required fields. No scoring or repair is run.
4. Emit the entire candidate as `angle`, changing only the identity key from `angle_id` to `external_id`; map every `supporting_claim_ids` value to the matching checkpoint claim `external_id` without changing the string values.
5. Require `angles.json.run_id` to equal `source_run_id` when present. Do not use the `recommended_angle_id` as a substitute for the selected marker.

The five proposal-provided scoring dimensions (`audience_relevance`, `novelty`, `hook_strength`, `visual_potential`, `explainability`) are copied exactly. `evidence_strength`, `controversy_risk`, `total_score`, `eligibility`, `rejection_codes`, and `originality` are copied exactly from the already recorded candidate; they are not recomputed. Semantic fields such as `hook`, `core_question`, and `core_insight` are copied exactly. The `AngleCandidate` contract is unchanged.

### Script

- `script.external_id` ← `script.json.script_id`.
- `script.angle_external_id` ← `script.json.angle_id`; it must equal `angle.external_id`.
- `title`, `target_duration_seconds`, `speaking_rate_chars_per_second`, `spoken_character_count`, and `estimated_duration_seconds` ← exact `script.json` values.
- `script.text` ← exact `script.md` text.
- For each `script.json.sentences[]`, copy `sentence_id` to `external_id`, plus `section`, `sentence_type`, exact `text`, and `claim_ids`.
- Compute `byte_start` / `byte_end` as UTF-8 byte offsets into the exact `script.text`; verify that slicing those bytes decodes to the exact sentence text, in order, and that all non-whitespace text is covered exactly once. Any mismatch fails; do not trim or repair.
- `evidence_ids` is `[]` for native scripts because the current formal script artifact carries `claim_ids`, not evidence IDs. Do not invent sentence-to-evidence links.

### Claims and evidence

Each native facts claim maps as follows:

| V2 checkpoint field | Native `facts.json` field |
|---|---|
| `external_id` | `claim_id` |
| `proposition` | `claim_text` |
| `classification` | `claim_type` |
| `verification_status` | same |
| `rationale` | `verification_reason` |
| `allowed_downstream` | same |
| `source_ids` | same, after verifying every source ID exists |
| `evidence_ids` | deterministic IDs assigned to the nested evidence rows, in their original order |
| `native_metadata.domain`, `risk_level`, `script_usage` | same native values when present |

Each nested claim evidence row is flattened once, in claim order then evidence order:

- `external_id` is a deterministic ID derived from the owning claim ID and one-based evidence ordinal; it must be unique in the checkpoint.
- `claim_ids` is the single owning claim ID.
- `source_ids` is `[evidence.source_id]`.
- `relation`, `evidence_text`, `source_section`, `paragraph_locator`, `published_at`, and `retrieved_at` are copied exactly.
- `excerpt_anchor` is copied exactly from `evidence_text`; validation requires it to be non-empty and present in the indexed source snapshot. It is not paraphrased or shortened.
- `original_url` must match the referenced source's exact URL; it is checked, not used to infer a source row.

Duplicate evidence rows remain separate rows; V1 does not deduplicate or merge their text. Missing claims/evidence or broken references fail validation.

## 8. Facts 2.1 → checkpoint / formal facts mapping

Native fact generation currently emits schema version `2.1`; the existing importer target schema is `2.0`. The authoring conversion is structural and preserves text and evidence order.

1. Record native `schema_version`, `policy_version`, and `summary` under checkpoint `facts_source` for audit. The source file's exact hash is also in `protected_artifact_hashes`.
2. Convert each native claim using the mapping in Section 7. Preserve `domain`, `risk_level`, and `script_usage` under `native_metadata`; the V2 materializer copies these optional metadata values into the output claim without altering them.
3. Flatten native nested evidence to top-level checkpoint `evidence` and link it through generated stable external IDs. The V2 materializer resolves those IDs to canonical `evidence_NNN` IDs and embeds exact `evidence_text` under the formal claim.
4. Output formal facts with `schema_version: "2.0"`, canonical `run_id`, the existing importer policy identity, required V0.2 fields, and exact claim/evidence semantic text. `checked_at` is import-time audit metadata, not a replacement for native fact content.
5. Validate the emitted document against `docs/v0.2/facts.schema.json`. Do not pass native `facts.json` through unchanged and do not relabel `2.1` as `2.0` without mapping.

If a native claim lacks a required V0.2 field or cannot be mapped without changing its semantic text, authoring fails before approval.

## 9. Source official-review metadata

Every V2 source row must contain both `official: true` and an `official_review` record with:

- `decision: "approved_official"`;
- non-empty `reviewer`;
- timezone-aware ISO-8601 `reviewed_at`; and
- non-empty `basis` describing the explicit review basis.

This is a human-supplied/source-reviewed assertion. No authoring code may infer or set `official=true` from `credibility_tier`, `source_type`, URL, domain, or source content. If metadata is absent, contradictory, or says non-official, validation fails before approval and importer staging. The overall checkpoint reviewer separately approves the complete body; V1 does not require the source reviewer and checkpoint reviewer to be the same person.

The importer continues to require HTTPS and its existing allowlist/provenance rules. V2 adds the requirement that the explicit official-review record is present and body-hash-bound; it does not relax existing restrictions.

## 10. Source snapshot hash contract

`source_documents/index.json` has these concrete hash semantics in the current writer (`src/fanglei/pipeline.py`):

- `documents[].content_hash` and the `normalized_text` file hash are SHA-256 of the exact UTF-8 encoding of `doc.text`, written to `source_documents/<source_id>.md`. This is the source fetcher's extracted text string; the index writer does not apply another canonicalization pass.
- A `raw_response` JSON asset is the decoded response string written as UTF-8 text; its hash is `sha256_text(raw_content)`, not a guaranteed hash of original wire bytes.
- A `raw_response` PDF asset is the original PDF bytes; its hash is `sha256_bytes(raw_bytes)`.
- A `page_index` asset is the exact serialized JSON file bytes; its hash is `sha256_bytes(file_bytes)`.
- There is no uniform raw-source-byte hash on every document row. The separate `document_hash` row property is fetcher-defined and is not a V2 capture-hash contract.

At authoring and final pre-seal validation, `ArtifactRegistry` verifies the index artifact, normalized text, every indexed file, registry content hashes, and dependency freshness. The authoring layer writes `snapshot.source_text_sha256`, `snapshot.raw_capture_bytes_sha256` (only when the index has a matching raw PDF byte asset; otherwise `null`), and every role/path/hash in `snapshot.indexed_file_hashes`, using the explicit `hash_kind` mapping above. All are part of the approved body hash. These hashes document and bind the source-run snapshot; the source run itself is not a post-seal import dependency.

At V2 import, for each exact allowlisted URL, first load and verify any existing pinned capture; if none exists, fetch with the existing no-redirect HTTPS fetcher. Before pinning a newly fetched capture or materializing artifacts, compute `sha256_bytes(capture.content)` and compare it to `raw_capture_bytes_sha256` when that field is non-null. Then compute `sha256_text(_text_from_capture(capture))` with the importer's existing capture text extractor and compare it exactly to `source_text_sha256`. Only a capture that passes these checks may be newly pinned. A mismatch against an existing pin fails without refreshing or replacing it. A missing/invalid required digest, URL mismatch, stale cache, changed raw PDF, extraction failure, or text-hash mismatch fails closed with `SOURCE_SNAPSHOT_MISMATCH` or a more specific provenance error. The importer does not compare authoring's `indexed_file_hashes` to the vanished source run; those are approval-time audit evidence. It verifies evidence anchors against the captured extracted text while preserving the approved evidence text exactly. No substring-only substitute for hash equality is allowed.

The native source fetcher and importer's `_text_from_capture()` are distinct extraction paths and are not assumed to produce the same text. A source is importable under V2 only if the importer's extracted-text digest exactly matches the approved `source_text_sha256`; otherwise V2 fails closed. This may exclude source formats/adapters whose native text cannot be reproduced by the current importer extractor, including transformed API responses. Supporting those formats requires an explicitly versioned extractor contract in a future design revision; it does not permit weakening the equality check.

## 11. Approval record contract

The top-level V2 `approval` object requires exactly:

| Field | Requirement |
|---|---|
| `status` | Literal `approved`; draft/validated objects have no approval record. |
| `reviewer` | Non-empty explicit reviewer identifier. |
| `approved_at` | Timezone-aware ISO-8601 timestamp. |
| `body_sha256` | Exact canonical body hash shown to the reviewer and recomputed at seal and import. |

The human review operation receives the validated draft and expected digest. It must compare the supplied digest to the current digest and must not generate an approval automatically. Approval values are audit metadata; the body is the content being approved.

## 12. Approval invalidation rules

Approval is invalid if any of the following occur:

- any canonical body field changes, including angle, script, facts, research, source identity, official review metadata, source snapshot hashes, or protected artifact hashes;
- recomputed body SHA-256 differs from `approval.body_sha256`;
- during authoring, validation, or final pre-seal validation, a source-run artifact hash differs from `protected_artifact_hashes` or the case binding changes;
- a source capture or cache entry differs from its approved snapshot hash; or
- the approval record is missing, malformed, or not `approved`.

Before sealing, source-run changes invalidate the pending draft/approval and require rebuilding, revalidation, and new approval. After sealing, the run's later mutation or absence does not invalidate the sealed checkpoint; the importer validates the protected checkpoint body and source snapshots without consulting the original run. A body change still invalidates approval. A timestamp-only edit inside the body is a body change; approval metadata timestamps are outside the body.

## 13. Identity and cross-run protections

The authoring builder opens one `source_run_id` and reads every source input from that run directory only. It verifies:

- manifest `run_id`, registered binding artifact `run_id`, requested `source_run_id`, and requested `case_id` agree;
- the binding artifact and all required source artifacts are valid/current in `ArtifactRegistry`; their exact hashes are copied into `protected_artifact_hashes`;
- `facts.json.run_id` and `angles.json.run_id`, when present, match the manifest;
- selected angle ID in `angle.md` identifies exactly one candidate from that run's `angles.json`;
- `script.json.angle_id` equals the selected candidate's ID;
- angle support claims, script claim references, claim source references, evidence references, and source IDs all resolve within that checkpoint; and
- all source documents and protected artifact hashes resolve under that run, with no path traversal.

`checkpoint_id` is unique within its case storage path. At final seal, authoring repeats the manifest/binding checks and validates every protected source artifact; any identity, freshness, or hash change prevents sealing and invalidates the approval. The sealed body retains `source_run_id` and `protected_artifact_hashes` as immutable approval-time provenance/audit evidence. Importer V2 verifies the checkpoint's own identity and references but never reads `runs/<source_run_id>/`; the sealed checkpoint remains importable when that directory is absent. Same-run provenance is established by authoring/validation/final seal and approved as part of the body; after seal, importer verifies body integrity and internal consistency but does not independently re-prove source-run membership. GDP artifacts and fixtures are never source-run inputs.

### Normative source-run-to-case binding

The single binding location is `<run_dir>/checkpoint_authoring_binding.json`, registered as the `checkpoint_authoring_binding` artifact in `ARTIFACT_GRAPH` with no artifact dependencies. Its exact object is `{"schema_version":"checkpoint-authoring-binding/1.0","run_id":"<run-id>","case_id":"<case-id>"}`. `RunManifest` remains without a top-level `case_id`; its `artifacts` map records the binding artifact's valid state and content hash.

`bind_source_run_to_case(run_id, case_id, runs_dir)` requires both IDs explicitly, verifies that the selected run manifest and run directory identify `run_id`, and creates the binding artifact once using atomic create-if-absent semantics. It then records the exact artifact hash as valid in the run manifest. The binding artifact's registry content hash is included in `protected_artifact_hashes`, so the binding is inside the same authoring freshness/hash boundary as the other required inputs. The binding has no dependencies on mutable content artifacts; each content artifact's freshness is validated independently.

If a valid registered binding file already contains the exact same schema, `run_id`, and `case_id`, the operation validates its registry hash and returns idempotently without writing. If the requested binding conflicts with the existing value, or a file/state exists but is malformed, stale, missing, or hash-inconsistent, it fails closed and never rewrites or adopts the value. There is no binding inference from slug, title, or filesystem path.

## 14. Sealed storage and write-once rules

The exact V1 storage path is:

```text
cases/<case-id>/approved-checkpoints/<checkpoint-id>.json
```

The directory is created under the repository root if needed. The path must be under a non-ignored case directory that is expected to be Git-tracked. IDs are validated as safe single path components; absolute paths, separators, `.`/`..`, and traversal are rejected. The sealed file is a complete V2 envelope, including the approval record. Draft and validation objects are in-memory only in V1; they are not written to `runs/` or `.checkpoint-staging/`.

Sealing is write-once:

- if the path does not exist, publish the complete JSON atomically;
- if it exists and its canonical full envelope is identical, return the existing path idempotently;
- if it exists with any different body or approval record, fail with `CHECKPOINT_WRITE_ONCE_CONFLICT`; never overwrite, rename, or delete it.

The operation must be race-safe: a check-then-`os.replace` sequence that can overwrite a concurrently created file is insufficient. The implementation must use an atomic no-replace publication strategy or an equivalent per-ID lock. `seal_checkpoint()` does not inspect or manage Git state and never runs `git add`, commit, or push. Git commit/push is a separate human-controlled closeout.

`.checkpoint-staging/` remains exclusively importer staging. `runs/` remains formal run artifacts and is not long-term checkpoint storage.

## 15. Importer V2 verification responsibilities

Before materializing formal artifacts or promoting, `CheckpointImporter` V2 must:

1. dispatch by exact `checkpoint_schema_version` and retain the legacy V1 validation path unchanged;
2. parse a strict V2 envelope and reject unknown/missing fields;
3. recompute canonical body SHA-256 and compare it with `approval.body_sha256`;
4. require approved status, reviewer, and approved_at;
5. validate `checkpoint_id`, `case_id`, `source_run_id` as checkpoint provenance identity, and validate all checkpoint-internal IDs/references; do not open or require `runs/<source_run_id>/`;
6. require explicit source official-review metadata and valid HTTPS source rows;
7. resolve captures after body-level preflight, validate each capture's raw-byte hash when present and exact extracted-text hash against the approved source snapshot, then pin a new capture only after a match and before materialization;
8. preserve existing `AngleCandidate`, facts/script schema, ID/reference, source excerpt, fact-coverage, and script-coverage gates; and
9. preserve existing stage-only behavior on any failed gate, with no production promotion.

V2 output remains in `.checkpoint-staging/cp-<fingerprint-prefix>/`; successful `import_checkpoint()` promotion remains atomic into `runs/<run_id>/`. The import manifest records the canonical body hash, V2 checkpoint fingerprint, source snapshot hashes, pinned capture hashes, ID mapping hash, semantic artifact hashes, and gates. `checkpoint_content_sha256` remains an importer metadata field only; for V2 its value is the verified `approval.body_sha256`, while legacy V1 retains its existing calculation. The authoring layer must not duplicate or bypass importer gates.

Inspection of the current `CheckpointImporter.stage()` confirms it reads the supplied checkpoint and source captures; it does not read `source_run_id` or require the source run directory. No existing importer security guarantee depends on that directory. V2 keeps this independence; authoring-time same-run proof is recorded in the body as approval-time provenance, while import-time guarantees are the independent checks listed above.

## 16. Legacy V1 compatibility boundary

- `1.0` and `approved-checkpoint/1.0` retain their prior meaning and validation behavior. V1 does not reinterpret old approval metadata as hash-bound approval.
- V2 authoring emits only `approved-checkpoint/2.0` and always includes all required V2 identity, protected hash, source snapshot, and approval fields.
- Import dispatch is explicit by version. It must never silently upgrade, down-convert, backfill, or infer fields for a V1 checkpoint.
- V1 checkpoints continue through the legacy branch under its existing gates. They do not gain V2 guarantees retroactively.
- The blocked Fed checkpoint remains blocked; no V2 builder may treat it as an authoring input without new, fully approved source artifacts.

## 17. Failure and error categories

V1 should expose stable machine-readable categories; exact Python exception classes are an implementation detail.

| Category | Example code | Meaning |
|---|---|---|
| Input artifacts | `AUTHORING_ARTIFACT_MISSING`, `AUTHORING_ARTIFACT_STALE`, `UPSTREAM_ARTIFACT_HASH_MISMATCH` | Required source artifact is absent, stale, or changed. |
| Identity | `CHECKPOINT_IDENTITY_MISMATCH`, `CASE_BINDING_MISSING`, `CROSS_RUN_REFERENCE` | Case, run, angle, script, claim, source, or evidence binding does not resolve. |
| Angle | Existing `ANGLE_FORMAL_FIELDS_MISSING`, `ANGLE_INVALID`, `ANGLE_NOT_ELIGIBLE` | Full existing candidate contract is not met; no filling/defaulting occurs. |
| Facts/script | `FACTS_MAPPING_INVALID`, `SCRIPT_OFFSETS_INVALID`, existing facts/script schema issue | Mapping or formal schema validation fails. |
| Source review/provenance | `SOURCE_OFFICIAL_REVIEW_MISSING`, `SOURCE_NOT_ALLOWLISTABLE`, `SOURCE_SNAPSHOT_MISMATCH`, existing `PROVENANCE_*` / `SOURCE_CONTENT_CHANGED` | Official status, HTTPS allowlist, snapshot, capture, or evidence excerpt fails. |
| Approval/seal | `APPROVAL_BODY_HASH_MISMATCH`, `CHECKPOINT_NOT_APPROVED`, `CHECKPOINT_WRITE_ONCE_CONFLICT` | Approval is absent/stale or the immutable path conflicts. |
| Import gates | Existing schema, provenance, fact-coverage, and script-coverage gates | Importer must stop before promotion when any gate fails. |

Errors must identify the failing field/path without exposing secrets or changing files outside the operation's intended output path.

## 18. Minimal Python API proposal

V1 is Python API-first, matching the current importer surface. Proposed public functions (names are implementation detail; contracts are normative):

```python
bind_source_run_to_case(run_id, case_id, runs_dir) -> None  # one-time, explicit binding
build_checkpoint_draft(run_id, case_id, checkpoint_id, runs_dir,
                       official_reviews) -> CheckpointDraft
validate_checkpoint_draft(draft, runs_dir) -> ValidationReport
approve_checkpoint(draft, validation, *, reviewer, expected_body_sha256,
                   approved_at=None) -> CheckpointApproval
seal_checkpoint(draft, approval, repository_root) -> Path
import_sealed_checkpoint(path, importer) -> ImportResult
```

`CheckpointDraft` is body-only and cannot be passed as approved input. `approve_checkpoint` requires a passing report and an exact expected digest. `seal_checkpoint` recomputes the digest and enforces the fixed storage path/write-once policy. `import_sealed_checkpoint` parses the sealed file and delegates to the V2-enabled `CheckpointImporter`; it does not duplicate staging/promotion logic.

`bind_source_run_to_case` always takes explicit IDs. First call creates the registered binding artifact; a matching existing binding is validated and idempotent, while any conflicting, malformed, stale, or unregistered existing binding fails without overwrite. Whether reviewer timestamps are caller-supplied or generated as timezone-aware UTC is an implementation detail, but the persisted format is fixed to timezone-aware ISO-8601.

## 19. CLI scope decision

No checkpoint authoring or import CLI commands are added in V1. The existing importer is Python API-only, and a CLI is not required to establish the explicit approval/hash boundary. A caller must present the draft and digest to a human, then call the explicit approval API with that exact digest and reviewer. No function may approve during build, validate, seal, or import.

This decision does not prohibit a later local CLI proposal; it keeps V1 free of UI and command-surface expansion.

## 20. Minimal implementation phases

1. **Contract and models:** implement strict V2 body/envelope/approval types, version dispatch, canonical JSON helper, and explicit source-run case binding. Preserve legacy V1 behavior.
2. **Deterministic authoring:** implement artifact loading, freshness/identity checks, exact mappings, source official-review input, and a pure validation report. No provider or network call in draft/validation.
3. **Approval and seal:** add explicit digest-confirming approval, canonical body hash verification, safe path handling, atomic write-once publication, and case storage tests.
4. **Importer V2:** verify approval/body hash, checkpoint-internal identity/references, source snapshot hashes, and V2 mappings before materialization; preserve every existing importer gate and stage/promotion behavior without reopening the source run.
5. **Documentation and acceptance:** document API usage, errors, storage, and legacy boundary; complete the test matrix and acceptance criteria before considering V1 implemented.

## 21. Full test matrix

### Contract and canonical hash

- V2 requires the exact version and every required identity/body/approval field; unknown V2 fields fail.
- Canonical body hash is stable across JSON key order and indentation but changes for every protected value, list-order change, exact text change, source snapshot hash change, or protected artifact hash change.
- `approval` is excluded from body hash; approval body hash is validated separately. Legacy V1 fingerprint and approval behavior remain unchanged.
- Reject malformed, uppercase/non-hex, wrong-length, absent, or mismatching `body_sha256`.

### Deterministic artifact assembly

- Identical valid source artifacts and explicit review metadata produce identical body bytes/hash regardless of process time.
- Candidate is selected by `angle.md`; missing/duplicate candidate, rejected candidate, incomplete `AngleCandidate`, missing selected marker, or mismatch with `script.json.angle_id` fails.
- Exact semantic angle fields and scoring/derived fields survive unchanged; authoring never calls `score_angles`, `select_angle`, or a provider.
- `research.md`, script text, claim text, and evidence text are byte-for-byte preserved.
- UTF-8 multibyte script sentences get correct byte offsets; whitespace, overlap, missing text, reordered sentences, or uncovered non-whitespace fails.
- Deterministic evidence IDs are unique and stable; duplicate evidence is retained in order; every claim/source/evidence/angle/script reference resolves.

### Facts mapping and schemas

- Native facts schema 2.1 maps to V2 checkpoint rows and importer formal facts schema 2.0 with exact text and stable IDs.
- Preserve supported native claim metadata; preserve native schema/policy/summary in `facts_source`.
- Missing required claim/evidence fields, invalid enums, empty required text, or unsupported mapping fails before approval.
- Materialized facts validate against `docs/v0.2/facts.schema.json`; script validates against `docs/v0.3/script-contract.schema.json`.

### Sources and snapshots

- Missing/false official status or incomplete `official_review` fails; `credibility_tier`, `source_type`, and URL never supply the value.
- Non-HTTPS, URL mismatch, source ID mismatch, missing index entry/hash/file, invalid hash kind, or a declared raw PDF hash that cannot be tied to a capture fails closed.
- The exact `sha256_text(_text_from_capture(capture))` must equal `snapshot.source_text_sha256`; when `raw_capture_bytes_sha256` is non-null, `sha256_bytes(capture.content)` must also match. A one-byte raw-PDF mutation, extraction/text mismatch, stale cache mismatch, redirect, or changed source fails before materialization/promotion.
- Sources whose native extracted text cannot match the importer's extracted text fail closed; they are not normalized by inference or substring matching.
- Evidence excerpt anchor must exist in the exact approved snapshot; imported `evidence_text` remains exact.

### Identity and stale upstream

- Missing case binding, wrong run ID, wrong case ID, mismatched manifest, or protected artifact hash fails.
- Mix angle/script/facts/sources/research across two runs or cases; every cross-run combination fails.
- Mutating each protected upstream artifact or its indexed source document before final seal invalidates validation/seal and requires a new approval; mutating or deleting the source run after seal does not block import.
- Path traversal in case ID, checkpoint ID, source path, or run ID is rejected.

### Approval, sealing, and import

- Draft and validated objects cannot be staged/imported; status other than approved or absent reviewer/time fails.
- Changing any body field after approval rejects seal and import with approval hash mismatch.
- Same checkpoint ID plus identical full envelope is idempotent; same ID plus changed body or approval is refused without changing the existing file.
- Concurrent attempts to seal one ID cannot overwrite or expose a partial file.
- Successful V2 import records body/fingerprint/source hashes and passes all four existing gates before promotion, even when the original source-run directory is absent.
- Any failed gate leaves no formal production run; the sealed checkpoint and prior pinned source capture remain unchanged.
- Existing V1 fixtures/imports continue to exercise only the legacy contract path.

## 22. Acceptance criteria

V1 is accepted only when all of the following are true:

1. New authoring outputs use exactly `approved-checkpoint/2.0`; legacy V1 semantics remain unchanged.
2. Draft assembly is deterministic and reads only current artifacts from one explicitly case-bound source run; authoring, validation, and final pre-seal validation verify its identity, freshness, and hashes.
3. The complete selected `AngleCandidate`, mapped facts/evidence, source snapshots, research, and script are preserved without semantic rewriting or generation.
4. V2 approval contains `status`, `reviewer`, `approved_at`, and the recomputed canonical body `body_sha256`.
5. Any protected body or source snapshot mismatch fails closed before promotion. Source-run artifacts are verified through final seal; their later mutation or absence does not block import.
6. A sealed checkpoint is written only at the non-ignored, expected Git-tracked path `cases/<case-id>/approved-checkpoints/<checkpoint-id>.json` and cannot be overwritten under the same ID with different content. Git add/commit/push is a separate human-controlled closeout; the authoring API does not manage Git.
7. `.checkpoint-staging/` remains importer-only staging; `runs/` remains formal run output storage.
8. Importer V2 independently verifies approval/body hash, checkpoint-internal identity/references, source snapshots/captures, schemas, provenance, coverage, and every existing gate before promotion, without requiring the source-run directory.
9. No code path auto-approves, fills missing `AngleCandidate` values, changes the angle contract, or weakens importer gates.
10. The full test matrix passes, with no test invoking TTS or a live provider by default.

The blocked Fed checkpoint is not an acceptance fixture and remains blocked unless new original approved source material becomes available.
