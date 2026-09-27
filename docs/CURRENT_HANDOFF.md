# Current Handoff

## V0.2 development status

- V0.1.0 is frozen; do not regenerate the Fed video or change the public `v0.1.0` Release as part of V0.2 planning.
- Active branch: `v0.2/generalize-video-workflow`, created from `origin/main` at `148d2ebdaee1437c038ead4631a5953d42b9a392`.
- Current phase: Phases 1A, 1B, 1C, 2A, 2B, and 3A.1 are complete on the V0.2 development branch. Phase 2A uses the shared fail-closed eligibility contract; Phase 2B records an explicit hash-bound human angle choice before Script generation/repair. Phase 3A.1 added run-bound evidence targets, generic table/narrative extraction, exact line/column and source-section locators, and deterministic revision parsing. Fed V0.1 run artifacts and the public release were not changed.
- Phase 1B generalizes DeepSeek script generation and repair, plus deterministic mock script generation. Its only remaining topic-specific provider mapping is isolated as a historical Fed V0.1 compatibility adapter.
- Phase 3A.1 status: case `bls-aug-2026-employment`, run `2026-09-27-001-bls-august-2026-employment-situation`. The two approved BLS documents, publication reviews, and authority package (`13680d96d487497ed19d95ecbd09ccbf213e732f6787dc066320e11ed44355d9`) remain unchanged. Source index/selection, `evidence_targets.json`, native Facts 2.2, Research Focus, and deterministic Research are registry-valid/current. Facts contain 71 claims: 9 verified, 1 conflicted, and 61 unverified. The nine verified target facts cover August payroll, unemployment, earnings, workweek, June/July revisions, and named industry movements; Research cites those nine eligible claims only. No BLS Angle, Script, or video was generated.
- The initial Phase 3A `GENERALIZATION_GAP` is recorded as a historical failed checkpoint and was addressed by generic evidence extraction/locator changes; there is no BLS-only parser. Synthetic tests cover multi-level tables, line-oriented tables, wrapped and inline sentences, exact locator reconstruction, revisions, and source-section context. The generic table parser also extracts 3,824 structured cells from each current BLS capture, while target-attested narrative evidence supplies the nine verified facts. Phase 3A.1 extraction-focused regression passed (88 tests), expanded extraction/checkpoint/artifact regression passed (188 tests), and safe non-integration regression passed (723 tests).
- Exact next action: human review the current BLS Facts and Research artifacts, then stop. Do not generate angles or proceed to Phase 3B until that review is complete. See [cases/bls-aug-2026-employment/CASE_STATE.md](../cases/bls-aug-2026-employment/CASE_STATE.md).
- Phase 2 and V0.2 are not complete. Read actual Git branch, HEAD, ahead/behind, and working-tree state before further work. The Fed V0.1 run and public release remain untouched. See [docs/v0.2/GENERALIZATION_PLAN.md](v0.2/GENERALIZATION_PLAN.md).

## Current public release

- The V0.1.0 Fed Case 2 Video MVP is implemented on `main` and has been pushed to the public repository: <https://github.com/motty63-ctrl/fenglei-economy-content-engine>.
- GitHub Release `v0.1.0` is published at <https://github.com/motty63-ctrl/fenglei-economy-content-engine/releases/tag/v0.1.0>; its `final.mp4` asset is public. The verified file SHA-256 is `8796c73d62bed1090a9bbf6af268f5b91406b36913954d944953955d157c564d`.
- The V0.1.0 implementation and release are public project state. The active V0.2 branch is a development branch based on the public `main` snapshot above; read actual Git state for its current HEAD and ahead/behind.

## Fed Case 2 status

Run: `2026-09-24-001-fed-sep-case-2-source-inventory` under `runs/2026-09-24-001-fed-sep-case-2-source-inventory/`.

The native Case 2 run and video MVP are complete. The run has the approved four-document Federal Reserve source package, reviewed publication dates, native Facts 2.2, the locked `research_focus.json` and current Research, five eligible angles, user-selected `angle_001`, an evidence-grounded script, human-approved Volcengine narration, sentence-level proportional timing, an eight-scene visual plan, and the verified MP4. See `docs/FED_CASE_2_DEMO.md` for the record.

The final video is `runs/2026-09-24-001-fed-sep-case-2-source-inventory/final.mp4`, approximately 74.633 seconds, 1080×1920, 30 FPS, H.264/AAC. Caption timing is proportional to normalized sentence length; it is not WhisperX word-level forced alignment.

No new Fed approved checkpoint was created, imported, or promoted. The original historical Fed checkpoint remains blocked by `ANGLE_FORMAL_FIELDS_MISSING`; it was not repaired, upgraded, reused, imported, or promoted. The source package's independent source count remains `1`, and its legacy `selection_status` remains `insufficient_sources`.

## Historical checkpoint boundary

The old checkpoint recovery remains closed. Do not repair, backfill, infer, default, copy, or upgrade its missing `AngleCandidate` fields. GDP artifacts and test fixtures are not valid Fed recovery sources.

## Handoff boundary

V0.1.0 remains frozen and public. Phases 1A, 1B, 1C, 2A, 2B, and 3A.1 are complete on the V0.2 branch. The BLS Facts and Research artifacts are ready for human review. Do not generate angles or proceed to Phase 3B in this handoff.
