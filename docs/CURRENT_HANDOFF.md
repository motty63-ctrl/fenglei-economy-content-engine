# Current Handoff

## V0.2 development status

- V0.1.0 is frozen; do not regenerate the Fed video or change the public `v0.1.0` Release as part of V0.2 planning.
- Active branch: `v0.2/generalize-video-workflow`, created from `origin/main` at `148d2ebdaee1437c038ead4631a5953d42b9a392`.
- Current phase: Phases 1A, 1B, 1C, 2A, 2B, 3A.1, and 3A.2 are complete on the V0.2 development branch. Phase 2A uses the shared fail-closed eligibility contract; Phase 2B records an explicit hash-bound human angle choice before Script generation/repair. Phases 3A.1/3A.2 add run-bound evidence targets, generic table/narrative extraction, exact locators, atomic propositions, scope-bound authority verification, and deterministic Research rendering. Fed V0.1 run artifacts and the public release were not changed. Generic atomic-authority safety alignment is committed at `a0ecb8be28ac911ecff3741a6330fa8d8339d828`.
- Phase 1B generalizes DeepSeek script generation and repair, plus deterministic mock script generation. Its only remaining topic-specific provider mapping is isolated as a historical Fed V0.1 compatibility adapter.
- Phase 3A review and Phase 3B angle planning: case `bls-aug-2026-employment`, run `2026-09-27-001-bls-august-2026-employment-situation`. A dependency-bound human approval record approves the current nine listed verified claims and deterministic Research for Angle Planning only. Generic atomic-authority safety is committed at `a0ecb8be28ac911ecff3741a6330fa8d8339d828`. The formal offline angle owner produced five eligible candidates; `angles.json` is current, and the human review packet is [cases/bls-aug-2026-employment/ANGLE_REVIEW.md](../cases/bls-aug-2026-employment/ANGLE_REVIEW.md). The system recommends `angle_004`; human selection is still pending. No `angle_selection.json`, Script, audio, storyboard, timeline, or video exists for this BLS run.
- Phase 3A.2 focused tests: 90 passed; safe non-integration regression: 729 passed. The original `GENERALIZATION_GAP` remains a historical failed checkpoint resolved by generic extraction work; production code added no BLS-specific branch. The separate existing GDP compatibility/calibration logic and generic month-name parsers are unchanged.
- Exact next action: review the five candidates in [cases/bls-aug-2026-employment/ANGLE_REVIEW.md](../cases/bls-aug-2026-employment/ANGLE_REVIEW.md) and, if desired, record one explicit human choice using the documented `select-angle` command. A system recommendation is not a human selection. Script generation remains blocked until the selection artifact is recorded.
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

V0.1.0 remains frozen and public. BLS Facts and Research have been approved for Angle Planning only, and five candidates have been generated. This handoff stops before human angle selection; it does not authorize Script, TTS, storyboard, timeline, or rendering. The original blocked Fed checkpoint and its recovery boundary remain unchanged.
