# Current Handoff

## V0.2 development status

- V0.1.0 remains frozen and public; its Fed demo and Release are unchanged.
- Active development branch: `v0.2/generalize-video-workflow`.
- Phases 1A, 1B, 1C, 2A, 2B, 3A.1, 3A.2, 3B.1, 3B.2, and 3C.1.2–3C.1.5 are complete. Earlier Phase 3C.1 / 3C.1.1 failures remain historical checkpoints; their validation gaps were addressed by later generic work.
- BLS Phase 3A human review approved the Facts/Research package for Angle Planning; five candidates passed the documented checks and the user selected `angle_001`. The current Script was human-approved for TTS with its existing hash-bound approval. No Script, Facts, Research, angle, terminology, or narration wording was changed during Phase 3C.2A.
- **Current phase: Phase 3C.2A completed production TTS and technical audio QA. Human Audio Review is pending.** The authorized Volcengine request generated the canonical combined WAV; its technical quality artifact passed. See [cases/bls-aug-2026-employment/AUDIO_REVIEW.md](../cases/bls-aug-2026-employment/AUDIO_REVIEW.md) for hashes, measurements, segment text, limitations, and the listening checklist.
- Phase 1B generalizes DeepSeek script generation and repair plus deterministic mock script generation; its remaining topic-specific mapping is isolated to a historical Fed V0.1 compatibility adapter.
- Phase 3A/3B for the BLS run produced five eligible angles from the current verified package; four of five Research Focus dimensions have direct eligible support, while survey-boundary support remains omitted. The user selected `angle_001`; the hash-bound selection and terminology artifacts remain current. The earlier `GENERALIZATION_GAP` is a historical checkpoint resolved by generic extraction work, with no BLS-specific production branch.
- Phase 3A.2 focused tests passed 90 and the safe non-integration regression passed 729 at that checkpoint. These are historical phase results, not the current audio-focused test result.
- The BLS run is `2026-09-27-001-bls-august-2026-employment-situation`. Audio is current against the approved Script and narration inputs. No human audio approval exists yet.
- **Exact next action: listen to the local narration WAV and complete the human decision in `AUDIO_REVIEW.md`.** Do not create an audio approval artifact until the human review is explicit. Alignment, subtitles, Storyboard, visual planning, Timeline, and MP4 rendering have not started for this BLS run.
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

V0.1.0 remains frozen and public. For BLS Case 2, the current Script has explicit human approval for TTS, one Volcengine narration file has been generated, and the existing technical audio QA passed. **The audio itself still awaits human listening review.** No audio approval artifact exists. The next authorized action is to listen to the local WAV and record a human decision using `cases/bls-aug-2026-employment/AUDIO_REVIEW.md`; alignment, subtitles, Storyboard, Timeline, and video remain unstarted for this BLS run. The original blocked Fed checkpoint and its recovery boundary remain unchanged.
