# Current Handoff

## Current Phase 3C.5C — corrected preview awaiting human review

**`V0.2_PHASE_3C5C_WAITING_FOR_PREVIEW_REVIEW` · `HUMAN PREVIEW REVIEW = PENDING`**

Preview Candidate 1 has the explicit human `CHANGES_REQUIRED / SUBTITLE_OCCLUSION_AND_TIMING_SYNC` decision. Preview Candidate 2 is `TECHNICAL_RENDER_FAILURE / RENDER_TIME_AND_SUBTITLE_LAYOUT`, never registered for human review; it is not a human rejection. Both videos and old renderer packages are preserved.

Generic renderer fix `0e587cc` binds scenes, motion and captions to requested HyperFrames frame time, independently of audio playback. Full subtitle text is measured after browser font resolution; compact panels adapt to actual wrapping and safe free bands without clipping or covering measured critical objects/footers. No BLS/Fed-specific rendering branches or added font files are used.

The formal owner reused Timeline Candidate 2 unchanged (SHA-256 `3e60ff14724751cef59d252e013c76950db37cacc30f99f515aa4e1db9da6642`) and generated renderer/preview Candidate 3. All previously existing run files except owner-updated `run.json` remain byte-identical. Current MP4: `runs/2026-09-27-001-bls-august-2026-employment-situation/review-preview-candidate-3.mp4`; SHA-256 `0421363e620e56429e8b14b3dead33b5fbdbf99f1b0eda1ecece917b9738f4fe`. It is NON-FINAL, 3,889,121 bytes, 1080×1920, 30 FPS, H.264/AAC, 58.700 s video / 58.679 s audio.

Actual QA covered 9 scene interiors, 6 boundary frames, all 12 subtitle cues, and opening/ending. The 27 scene/boundary/cue frames match the compiled DOM; scene_003 is correct and scene_008's three lines are visible. Both DOM probes report zero clipping/footer/critical-object collision. Focused tests: 49 passed; safe non-integration: 958 passed (zero failures/skips); diff check passed. Font fallback and large-HTML lint messages remain documented non-blocking limitations. Timing remains pause-refined sentence timing, not word-level forced alignment.

**Exact next action: human review of Preview Candidate 3 and `cases/bls-aug-2026-employment/PREVIEW_REVIEW.md`.** No preview approval, final render, publication, push, merge, or V0.2 completion is authorized by this phase.

## Historical V0.2 status through Phase 3C.5

- V0.1.0 remains frozen and public; its Fed demo and Release are unchanged.
- Active development branch: `v0.2/generalize-video-workflow`.
- Phases 1A, 1B, 1C, 2A, 2B, 3A.1, 3A.2, 3B.1, 3B.2, and 3C.1.2–3C.1.5 are complete. Earlier Phase 3C.1 / 3C.1.1 failures remain historical checkpoints; their validation gaps were addressed by later generic work.
- BLS Phase 3A human review approved the Facts/Research package for Angle Planning; five candidates passed the documented checks and the user selected `angle_001`. The current Script remains human-approved for TTS with its original hash-bound approval. Phase 3C.2B changed neither Script nor Facts/Research/angle/terminology content.
- **Historical Phase 3C.5 checkpoint: `PHASE_3C5_WAITING_FOR_PREVIEW_REVIEW`; its gate: `HUMAN PREVIEW REVIEW = PENDING`.** Audio Candidate 2 is approved for Storyboard. The recovered Storyboard remains approved through its hash-bound record; Visual Candidate 1 and Candidate 2 retain their formal `CHANGES_REQUIRED` reviews. Candidate 3 bundle SHA-256 `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355` was explicitly approved for Timeline by `motty63-ctrl`; the review is bound to the recovered Storyboard and current upstream hashes. The formal Timeline owner generated a 5.1 composition with 9/9 scenes, 12 subtitle cues, and the unchanged 58,679 ms audio. A local `PREVIEW · NOT FINAL` renderer project is ready for human inspection; no final video render/export occurred. Alignment remains estimated proportional sentence timing. See [PREVIEW_REVIEW.md](../cases/bls-aug-2026-employment/PREVIEW_REVIEW.md), [CASE_STATE.md](../cases/bls-aug-2026-employment/CASE_STATE.md), [VISUAL_REVIEW.md](../cases/bls-aug-2026-employment/VISUAL_REVIEW.md), and [AUDIO_REVIEW.md](../cases/bls-aug-2026-employment/AUDIO_REVIEW.md).
- Phase 1B generalizes DeepSeek script generation and repair plus deterministic mock script generation; its remaining topic-specific mapping is isolated to a historical Fed V0.1 compatibility adapter.
- Phase 3A/3B for the BLS run produced five eligible angles from the current verified package; four of five Research Focus dimensions have direct eligible support, while survey-boundary support remains omitted. The user selected `angle_001`; the hash-bound selection and terminology artifacts remain current. The earlier `GENERALIZATION_GAP` is a historical checkpoint resolved by generic extraction work, with no BLS-specific production branch.
- Phase 3A.2 focused tests passed 90 and the safe non-integration regression passed 729 at that checkpoint. These are historical phase results, not the current audio-focused test result.
- The BLS run is `2026-09-27-001-bls-august-2026-employment-situation`. Candidate 2 is current against the approved Script and narration inputs. Human audio approval SHA-256 is `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f`; alignment SHA-256 is `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306`; subtitle SHA-256 is `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46`.
- **Historical Phase 3C.5 next action (superseded above): human preview review** using [PREVIEW_REVIEW.md](../cases/bls-aug-2026-employment/PREVIEW_REVIEW.md) and `runs/2026-09-27-001-bls-august-2026-employment-situation/renderer_project/review-preview.html`. Review pacing, motion, subtitle/audio sync, legibility, scene continuity, and ending. Do not approve a final render or export from this packet; a separate human decision is required.
- Phase 2 and V0.2 are not complete. The Fed V0.1 run and public Release remain untouched. See [docs/v0.2/GENERALIZATION_PLAN.md](v0.2/GENERALIZATION_PLAN.md).

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

The current target is Preview Candidate 3, registered/current and awaiting explicit human review. Candidate 1's human rejection and Candidate 2's technical failure remain preserved. Approved upstream content and Timeline Candidate 2 remain unchanged. No final-render approval, final video export, publication or V0.2 completion is recorded. V0.1.0 and the old blocked Fed checkpoint remain unchanged.
