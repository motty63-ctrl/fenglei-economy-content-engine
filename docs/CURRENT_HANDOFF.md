# Current Handoff

## V0.2 development status

- V0.1.0 is frozen; do not regenerate the Fed video or change the public `v0.1.0` Release as part of V0.2 planning.
- Active branch: `v0.2/generalize-video-workflow`, created from `origin/main` at `148d2ebdaee1437c038ead4631a5953d42b9a392`.
- Current phase: Phases 1A, 1B, 1C, 2A, 2B, 3A.1, 3A.2, 3B.1, and 3B.2 are complete. Phase 2A supplies the shared fail-closed eligibility rule; Phase 2B records an explicit hash-bound human angle choice before Script generation/repair. Phases 3A.1/3A.2 add run-bound evidence targets, generic extraction, exact locators, atomic propositions, scope-bound authority verification, and deterministic Research rendering. Phase 3B.2 adds Focus coverage metadata, editorial quality checks, diversity checks, and auditable recommendation components. For the BLS run, five eligible angles were generated and `angle_001` was explicitly selected by the user. Phase 3C.1/3C.1.1 remain historical blocked checkpoints for the cross-language trust gap. Phase 3C.1.2 provides the generic terminology and script-quality foundation. Phase 3C.1.3 records the approved BLS terminology decisions: 40 approved mappings, six numeric entries rejected as non-terminology, and zero pending; the formal map is bound to current Facts SHA `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882` and has SHA `a9ee561650535b58d3c6f5bb36c30a884225f70c202f6f0923e2954f05262d2c`. Focused validation passed 103 tests and safe non-integration regression passed 796. No Script retry has yet been made. Fed V0.1 run artifacts and the public release were not changed.
- Phase 1B generalizes DeepSeek script generation and repair, plus deterministic mock script generation. Its only remaining topic-specific provider mapping is isolated as a historical Fed V0.1 compatibility adapter.
- Phase 3A review and Phase 3B angle planning: case `bls-aug-2026-employment`, run `2026-09-27-001-bls-august-2026-employment-situation`. A dependency-bound human approval record approves the current nine verified claims and deterministic Research for Angle Planning only. Phase 3B.2 generated five eligible candidates that pass authority-safety, editorial-quality, and diversity checks. Current `angles.json` SHA-256 is `32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8`; four of five Research Focus dimensions have direct eligible support, and the survey-boundary dimension remains unsupported. The user selected `angle_001`; the hash-bound `angle_selection.json` SHA-256 is `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77`. The terminology review packet is [cases/bls-aug-2026-employment/TERMINOLOGY_REVIEW.md](../cases/bls-aug-2026-employment/TERMINOLOGY_REVIEW.md). No valid Script, audio, storyboard, timeline, or video exists for this BLS run.
- Phase 3A.2 focused tests: 90 passed; safe non-integration regression: 729 passed. The original `GENERALIZATION_GAP` remains a historical failed checkpoint resolved by generic extraction work; production code added no BLS-specific branch. The separate existing GDP compatibility/calibration logic and generic month-name parsers are unchanged.
- Exact next action: after the terminology closeout commit, revalidate upstream dependencies and the formal Script entry; then run one bounded initial Script generation with at most two repairs. If validation succeeds, prepare `cases/bls-aug-2026-employment/SCRIPT_REVIEW.md` and stop for human Script review. Do not regenerate Facts, Research, angles, or selection, and do not begin TTS/video.
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

V0.1.0 remains frozen and public. BLS Facts and Research have been approved for Angle Planning only, and `angle_001` has been explicitly selected. The BLS terminology map is now human-approved and current; the next authorized action is a bounded Script generation/repair attempt after dependency revalidation. Any valid Script must receive separate human review before voice production. TTS, storyboard, timeline, and rendering are not authorized by this handoff. The original blocked Fed checkpoint and its recovery boundary remain unchanged.
