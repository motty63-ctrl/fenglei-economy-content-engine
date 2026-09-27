# Current Handoff

## V0.2 development status

- V0.1.0 is frozen; do not regenerate the Fed video or change the public `v0.1.0` Release as part of V0.2 planning.
- Active branch: `v0.2/generalize-video-workflow`, created from `origin/main` at `148d2ebdaee1437c038ead4631a5953d42b9a392`.
- Current phase: Phase 1A complete — Search and Research Focus generalization. Focused tests: 55 passed; safe non-integration regression: 676 passed. Fed run artifacts and the public V0.1.0 release were not changed.
- Phase 1B (content provider prompts) is next and has not started. Review [docs/v0.2/GENERALIZATION_PLAN.md](v0.2/GENERALIZATION_PLAN.md) before authorizing it.
- The Phase 1A changes are committed locally on this branch and have not been pushed; read Git for the current ahead/behind state.

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

V0.1.0 remains frozen and public. Phase 1A is complete; wait for human review before starting Phase 1B or any other V0.2 implementation slice.
