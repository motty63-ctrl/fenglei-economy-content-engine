# Authoritative Primary Evidence Contract Closeout

This document closes the serialization and compatibility contracts for
authoritative-primary claim evidence. It does not implement source-policy
selection, claim verification, Fed Case 2 processing, or checkpoint 2.1
materialization.

## Native facts contracts

Native facts and checkpoint-imported formal facts are separate contracts even
though both are stored under the filename `facts.json`.

- `docs/v0.2/native-facts-2.1.schema.json` describes the current output of the
  native `research.verify_claims()` and `factcheck` pipeline. It preserves the
  current 2.1 status, script-usage, and downstream behavior. It does not accept
  `verification_basis`.
- `docs/v0.2/native-facts-2.2.schema.json` defines the next native contract.
  It adds required claim-level `verification_basis` while retaining the
  existing `verification_status` values.
- `docs/v0.2/facts.schema.json` remains the existing checkpoint-imported
  formal facts 2.0 contract. It is not the schema for native facts 2.1.

For native facts 2.2, the legal status/basis combinations are:

| `verification_status` | `verification_basis` | `allowed_downstream` |
|---|---|---|
| `verified` | `independent_corroboration` or `authoritative_primary_attestation` | May be true only for a fact that passes the complete downstream qualification rules; basis alone never makes it true. |
| `conflicted` | `none` | Must be false. |
| `unverified` | `none` | Must be false. |

Only a verified fact with a non-`none` basis may set `allowed_downstream=true`.
The field remains an independently computed gate result; this contract does not
equate `verified` with automatic downstream permission.

An authority-attested claim has an `authority_attestation` object containing:

- `kind`: `document_report` or `deterministic_document_comparison`;
- `source_ids`: the exact supporting source identities;
- `attribution`: the explicit attribution wording retained in the proposition;
- `scope`: `subject`, `measure`, `period`, `unit`, `statistic`, and `certainty`.

For a document comparison, at least two distinct source IDs are required. The
attestation describes what the official documents report and the comparable
scope of the reported values. It does not assert motive, causality, market
effect, or an unattributed external-world conclusion. The schema captures the
required scope fields; future verification and script-lint code must still
check that the excerpt supports them and that the proposition has not expanded
their meaning.

## Native `sources.json` 2.1

`docs/v0.2/sources-2.1.schema.json` and `src/fanglei/source_contract.py`
define the new source contract. `sources.json` 2.0 continues to parse on its
legacy path without migration. A new 2.1 artifact must carry an explicit
`source_policy`:

- `independent_sources/1.0` is the explicit ordinary-source policy;
- `authoritative_primary_set/1.0` carries the institution identity, an exact
  list of approved official-primary documents, and a human approval record.

The authority policy body also requires explicit nonblank `run_id` and
`case_id`; neither is inferred from a path, title, or source URL. Both values
are covered by `approval.package_sha256`. Checkpoint 2.1 additionally requires
them to equal its `source_run_id` and `case_id`, preventing an unchanged policy
approval from being reused for a different run or case.

Each approved document binds `source_id`, exact HTTPS URL, document identity,
evidence role, release date, explicit `official_primary` classification,
extracted-text SHA-256, and raw-capture-byte SHA-256 when available. The human
approval contains reviewer, timezone-aware approval time, rationale, and
`package_sha256`. That digest is SHA-256 over UTF-8 canonical JSON of the
`source_policy` body excluding the nested `approval` object, using sorted keys,
compact separators, unescaped Unicode, and no non-finite JSON numbers. This
avoids self-reference while binding the decision to the exact document list,
roles, dates, identities, and hashes.
Approved documents must have distinct `source_text_sha256` values as well as
distinct source IDs, URLs, and document identities. Different URLs or IDs do
not make duplicate normalized text count as distinct documents; duplicate
content fails closed.

The 2.1 artifact separately records:

- `package_admissibility`: whether the source package passes its selected
  source-policy requirements;
- `independent_source_count`: the number of distinct `independence_key` values
  among source rows marked `counts_as_independent`;
- `selection_status`: the existing independent-source gate, `selected` only
  when that count is at least three, otherwise `insufficient_sources`.

`package_admissibility` controls whether claim extraction may start under the
selected package policy. `selection_status` continues to express only the
independent-source gate for claims. An approved authority package may therefore
be `admissible` while its `independent_source_count` is `1` and its
`selection_status` is `insufficient_sources`. Those fields must never be
collapsed or substituted for one another. Under `independent_sources/1.0`, a
package cannot be admissible below the existing three-independent-source
threshold. A checkpoint cannot contain claims from any package marked
inadmissible. Existing 2.0 artifacts retain their current behavior because
they have no `package_admissibility` field.

Two rows marked `counts_as_independent=true` may not share an
`independence_key`. Distinct source IDs do not create independent sources when
their keys are the same. The source contract validates that the independent
count agrees with the distinct keys and that an authority allowlist exactly
matches the source IDs and URLs. It does not run the policy-selection
algorithm or alter any source artifact.

## Approved checkpoint 2.1

`approved-checkpoint/2.0` is frozen. It does not accept `verification_basis`,
source policy metadata, or any reinterpretation of its existing fields.
`1.0`, `approved-checkpoint/1.0`, and `approved-checkpoint/2.0` retain their
existing dispatch, hash, fingerprint, and materialization behavior.

The strict `approved-checkpoint/2.1` model in
`src/fanglei/checkpoint_contract.py` adds:

- `facts_source.schema_version: "2.2"`;
- the versioned `source_policy` and a `source_selection` record containing
  `package_admissibility`, actual `independent_source_count`, and the unchanged
  `selection_status`;
- per-source `credibility_tier`, `independence_key`, and
  `counts_as_independent` needed to preserve the independent-source record;
- claim `verification_basis` and an explicit nullable `authority_attestation`.

Authority claims must use an approved `authoritative_primary_set`; its
`run_id` and `case_id` must exactly match the enclosing checkpoint's
`source_run_id` and `case_id`. The checkpoint source rows must exactly match
its approved source IDs, URLs,
release dates, extracted-text hashes, and raw-capture hashes. Each authority
claim must retain the attribution text in its proposition, reference approved
sources, and have claim-linked supporting evidence with an excerpt and
location. A deterministic comparison must reference at least two approved
documents with distinct identities, evidence roles, and release dates. The
checkpoint model also enforces the legal status/basis combinations and keeps
`allowed_downstream` false unless the claim is a verified fact with a basis.
These are structural contract checks; they do not prove semantic entailment or
execute the authority verification algorithm. For `independent_corroboration`,
at least two distinct `independence_key` values must occur among the claim's
counted sources. At least one such source must have `credibility_tier` in
`{"A", "B", "C"}`, which is the exact persisted-source primary predicate in
native `research.verify_claims()`; an uncounted row cannot satisfy it.

Checkpoint 2.1 uses the existing approval boundary: canonical JSON body SHA-256
excludes only the top-level `approval` record. The resulting digest remains in
`approval.body_sha256`; source policy, selection record, basis, attribution,
and scope are all inside the hash-protected body. Explicit approval,
write-once sealing, and source snapshot hash semantics remain unchanged.

Version dispatch recognizes 2.1 separately. Importer materialization for 2.1
is not implemented in this phase and fails closed; it cannot fall through to
the legacy V1 path or the V2.0 materializer.

## Formal facts after checkpoint import

The `verification_basis` must remain present after import. The promoted
`facts.json` is consumed by the content pipeline's fact palette and script
linter, visual planning, storyboard validation, audit/review tooling, and
schema-based tests. Those consumers need to distinguish an independently
corroborated proposition from an attributed statement about a primary
document. Dropping the basis would leave `verified` and `allowed_downstream`
without their auditable explanation and could make later consumers treat a
document-attested claim as an unattributed world fact.

For checkpoint 2.1, the future materialized formal facts artifact therefore
uses the namespaced schema version `checkpoint-import-facts/2.1`, defined by
`docs/v0.2/checkpoint-import-facts-2.1.schema.json`. It preserves
`verification_basis` and `authority_attestation`. The namespace distinguishes
this formal importer projection from native facts 2.1, which has a different
shape. The canonical approval/provenance record remains the hash-bound
`approved_checkpoint.json`, including its source policy and source snapshots;
materialized facts are the downstream claim projection.

Legacy `1.0`, `approved-checkpoint/1.0`, and `approved-checkpoint/2.0`
continue to materialize the existing formal facts schema 2.0. No legacy
artifact is backfilled or relabeled.

## Downstream contract

A future runtime may permit `verified` plus
`authoritative_primary_attestation` into research, the fact palette, angle
supporting claims, and script `verified_fact` sentences only while preserving
the attested scope and explicit attribution. A script sentence such as “The
September SEP reports X” may be eligible when its evidence and scope pass.
Changing it to “X is true” or “X caused Y” is outside that attestation and must
fail unless another basis independently verifies the expanded proposition.

Neither package approval nor authority basis changes the independent source
count, lowers claim risk, bypasses evidence coverage, or grants downstream
permission on its own. Existing source, fact, script, and promotion gates
remain in force.

## Deferred implementation

This closeout establishes schemas, strict parsing, hash/identity bindings,
version dispatch, and contract tests only. It does not change the Fed run, run
source selection, generate facts or research, score/select angles, generate
scripts, build a checkpoint, approve, seal, import, or call a provider/network.
The next phase is **Authoritative Primary Evidence Runtime + Checkpoint 2.1
Materialization**, beginning with package admissibility and claim-basis
verification, then carrying the approved basis into the namespaced formal
facts 2.1 output while leaving all legacy branches unchanged.
