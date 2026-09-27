# Current Handoff

## V0.2 development status

- V0.1.0 is frozen; do not regenerate the Fed video or change the public `v0.1.0` Release as part of V0.2 planning.
- Active branch: `v0.2/generalize-video-workflow`, created from `origin/main` at `148d2ebdaee1437c038ead4631a5953d42b9a392`.
- Current phase: Phases 1A, 1B, 1C, 2A, 2B, 3A.1, and 3A.2 are complete on the V0.2 development branch. Phase 2A uses the shared fail-closed eligibility contract; Phase 2B records an explicit hash-bound human angle choice before Script generation/repair. Phases 3A.1/3A.2 add run-bound evidence targets, generic table/narrative extraction, exact locators, atomic propositions, scope-bound authority verification, and deterministic Research rendering. Fed V0.1 run artifacts and the public release were not changed.
- Phase 1B generalizes DeepSeek script generation and repair, plus deterministic mock script generation. Its only remaining topic-specific provider mapping is isolated as a historical Fed V0.1 compatibility adapter.
- Phase 3A.2 status: case `bls-aug-2026-employment`, run `2026-09-27-001-bls-august-2026-employment-situation`. Full evidence spans are preserved; each targeted narrative claim now has an exact atomic `proposition_span`, and its verified authority scope must match the registered target scope. Research displays the proposition, not a broader evidence sentence. The run was regenerated offline through formal owners; search/fetch stubs were not called. Sources, captures, approved package, and Research Focus content remain unchanged. Facts 2.2 remains at 71 claims (9 verified, 1 conflicted, 61 unverified); Research cites only the nine eligible facts. Industry coverage is partial (two increases and one decline), not a complete sector ranking. Current run registry artifacts are valid/current. No BLS Angle, Script, or video exists.
- Phase 3A.2 focused tests: 90 passed; safe non-integration regression: 729 passed. The original `GENERALIZATION_GAP` remains a historical failed checkpoint resolved by generic extraction work; production code added no BLS-specific branch. The separate existing GDP compatibility/calibration logic and generic month-name parsers are unchanged.
- Exact next action: human review the current BLS Facts 2.2 and deterministic Research artifacts, then stop. Status is `PHASE_3A_HUMAN_REVIEW_READY`, not approved. Do not generate angles or proceed to Phase 3B in this handoff. See [cases/bls-aug-2026-employment/CASE_STATE.md](../cases/bls-aug-2026-employment/CASE_STATE.md).
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
