# BLS Case 2 — Preview Candidate 3 Human Review

**Current state: `V0.2_PHASE_3C5C_WAITING_FOR_PREVIEW_REVIEW`**

**HUMAN PREVIEW REVIEW = PENDING · NON-FINAL · Final Render NOT approved**

Open [Preview Candidate 3](../../runs/2026-09-27-001-bls-august-2026-employment-situation/review-preview-candidate-3.mp4). This local, ignored MP4 is the current review target. Earlier previews and their audit evidence are preserved below.

## Current candidate identities

| Candidate | Status | SHA-256 |
|---|---|---|
| Preview 1 | Human `CHANGES_REQUIRED / SUBTITLE_OCCLUSION_AND_TIMING_SYNC`, reviewer `motty63-ctrl` | `d846da9f9688887ef7c91fb102fb4341d0f7e6c1f4c9e7fbcbf0b4d6a00fdde7` |
| Preview 2 | `TECHNICAL_RENDER_FAILURE / RENDER_TIME_AND_SUBTITLE_LAYOUT`; never registered for human review, not human-rejected | `5447663a0009d52381b5205138ee46edfcc97e68bd80ca74013fd1a5dba9d9d0` |
| Preview 3 | Current/valid; `PENDING_HUMAN_PREVIEW_REVIEW` | `0421363e620e56429e8b14b3dead33b5fbdbf99f1b0eda1ecece917b9738f4fe` |

Candidate 2 remains at `runs/2026-09-27-001-bls-august-2026-employment-situation/review-preview-candidate-2.mp4`, with its renderer package unchanged. Its technical defects were the opening visual at a scene_003 time and a clipped third subtitle line in scene_008. It did not reach the human gate.

| Frozen input / current renderer | SHA-256 |
|---|---|
| Timeline Candidate 2, reused without rebuilding | `3e60ff14724751cef59d252e013c76950db37cacc30f99f515aa4e1db9da6642` |
| Pause-aware refinement | `e007fb6a112a0c05f0a6ec5b7147975d3cf76ce3a14965db46e06e5f752581a3` |
| Preview Subtitle Track 2 | `bc872a3255594871210f0edf28d0842c0128a2a9d2cb0977f667153d1a0cca20` |
| Renderer package Candidate 3 | `b073d8cef8d50c4bb1b7f443adfabcf2b3773579912c9b20ddafc5d846572d1d` |
| Render manifest Candidate 3 | `52f058f0ccddeba34b58257c0a999c95e5cb75e9f2066d51dea941bc4a22acee` |

The generic renderer fix is commit `0e587cc` (`fix: make preview rendering timeline-deterministic`). A requested HyperFrames render time is now the single input to scene selection, fade progress, and caption selection. Audio is the approved mux track; its `currentTime` is not the visual clock. Browser fonts resolve before full-text DOM measurements; actual wrapped height grows the compact panel and selects a safe unoccupied band. No text is cropped, no font files were added, and no scene/case-specific branch was introduced.

## Candidate 3 technical QA

- One local HyperFrames 0.8.20 export, from the exact registered renderer package copied to an ignored execution directory; entry `review-preview.html`. No upstream content, old preview, or Timeline was overwritten.
- File: `review-preview-candidate-3.mp4`, **3,889,121 bytes**, H.264 / AAC, **1080 × 1920**, **30 FPS**, **1,761 frames**. Video/container duration **58.700 s**; audio **58.679 s**, matching the approved narration. Full video/audio decode passed.
- Actual MP4 frame audit: nine scene interiors, both sides of scene_006→007, scene_007→008, scene_008→009, all 12 cue midpoints, and opening/ending: **29 frames**. The 27 scene/boundary/cue frames matched compiled DOM captures (minimum SSIM `0.980973`). The opening starts at frame 0 with the intended object fade-in; ending retains the complete closing scene.
- At `14.72 s`, the actual frame shows scene_003 (earnings), not the opening Hook. At `50.0815 s`, scene_008 has all three subtitle lines visible.
- Source HTML and the actual compiled composition were both probed after font readiness. **12/12 full canonical subtitle texts**, zero overflow, zero footer collisions, zero critical-object collisions; font size **48 px**, actual panel heights **77 / 138 / 199 px**. The long cue is three lines; compact panel adaptation does not restore a giant lower-third.
- Native A/B/C frame smoke and 1/2/3-line Chinese subtitle tests passed. Focused renderer/playback regressions: **49 passed**; safe non-integration regression: **958 passed, 0 failed, 0 skipped**. `git diff --check` passed.
- All 124 prior run files except owner-updated `run.json` remain byte-identical, including approved Script/audio/Storyboard/visuals, canonical alignment/subtitle track, facts, Research, Timeline Candidate 2, Preview 1, and Preview 2.
- Canonical local audit: `runs/2026-09-27-001-bls-august-2026-employment-situation/artifacts/audit/preview-candidate-3/`: `render.log`, source/compiled DOM probes, `ffprobe.json`, `frame-validation.json`, `technical-qa.json`, and actual-frame PNGs. Technical QA JSON SHA-256: `3ad6345888ec84f8e961c81002b5d6e6db6ff2dd1a0066d569b54947f1e5578c`.

| Previous warning | Current classification |
|---|---|
| Narration `currentTime` control | **RESOLVED**: absent from export log; native requested frame time drives visuals independently of media seek. |
| Microsoft YaHei mapping/requirement | **RESOLVED**: no such requirement/warning in current composition. Generic CJK fallback mapping warnings remain **NON_BLOCKING**: actual browser geometry and compiled-frame QA passed; environment font availability can still affect typography. |
| Composition/timeline time metadata | **RESOLVED**: one root resolves duration `58.679`, dimensions `1080×1920`, FPS `30`, 1,761 frames. |
| Other renderer messages | **NON_BLOCKING**: large-HTML lint and a resource 404; all required assets, text, audio and sampled output validated. Compiler logs Inter font-face retrieval/caching and inline mapping; no font assets were installed/committed, and no LLM, TTS, image-generation, or external rendering service was used. |

## Human review checklist — current Candidate 3 only

- [ ] Listen for perceived pause-aware subtitle/audio synchronization; this is **sentence-level refinement**, not WhisperX or word-level forced alignment.
- [ ] Judge pacing, scene transition fades, and the opening/ending hold.
- [ ] Check the repositioned compact subtitle panels (some move above the data to avoid critical objects); technical non-collision is not an editorial approval.
- [ ] Inspect mobile readability, source footer visibility, and the three-line recap cue's line breaks.
- [ ] Decide whether changes are needed or the preview is ready for a separately authorized final-render decision.

No `human_preview_review_candidate_3.json` decision has been created. This packet grants neither final-render nor publication approval. V0.2 remains incomplete.

---

# Historical Preview Candidate 1 packet

The following original packet is preserved as historical evidence. Its pending gate and initial technical observations were superseded by the explicit human `CHANGES_REQUIRED` decision and subsequent technical checks above; it is not the current review target.

# BLS Case 2 — Timeline Preview Review

**Preview Candidate 1 decision: `CHANGES_REQUIRED`**

**Reason: `SUBTITLE_OCCLUSION_AND_TIMING_SYNC`**
**Reviewer: `motty63-ctrl`**

The reviewer accepted the visual direction but requested a smaller subtitle treatment and playback timing that follows natural pauses more closely. The observed scene-boundary offsets are review observations only; they are not target timestamps and must not be hardcoded. Script, audio, Storyboard, Visual Candidate 3, scene order, and factual content remain frozen.

**Current gate: `HUMAN PREVIEW REVIEW = PENDING`**

This is a local review preview, not a final video. No final-render approval or publication decision has been recorded.

## A. Approval chain

| Artifact | Current identity |
|---|---|
| Script | `runs/2026-09-27-001-bls-august-2026-employment-situation/script.json` — SHA-256 `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305`; human Script approval SHA-256 `8653415689546d56295f857722840de61f14d26515d836f077a1a13818e3c59f` |
| Audio Candidate 2 | SHA-256 `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183`; human audio review SHA-256 `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f` |
| Storyboard | Recovered canonical SHA-256 `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`; human Storyboard approval SHA-256 `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05` |
| Visual Candidate 3 | Bundle SHA-256 `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355`; human approval record `human_visual_asset_review_candidate_3.json` SHA-256 `a92d5d010c2ae2389ca8cd8c85da3bb5614dfaae684326e2e3390505004c11b3` |
| Alignment | SHA-256 `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306` |
| Subtitle track | SHA-256 `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46` |
| Timeline | `timeline.json`, schema `5.1`, SHA-256 `87730bfc54d84e5c1d2a10cdade67c9bea11dc4559a7915d5df6b19af8526d3a` |
| Local preview | `runs/2026-09-27-001-bls-august-2026-employment-situation/renderer_project/review-preview.html` — SHA-256 `0b77b76ded4713644e3d0dbd665a2c137e16516586535883db7e4a4d554bc31f`, 40,825 bytes |

The visual approval applies only to Candidate 3 and is bound to its current bundle, Storyboard, and upstream dependency hashes. Candidate 1 and Candidate 2 review records remain preserved.

## B. Timeline summary

All ranges are frozen from the approved Storyboard and cover the 58,679 ms audio without gaps or overlaps. Each scene uses a deterministic, staggered fade-in for the objects in its approved SVG. Motion changes presentation only; it does not change copy, values, claims, or their meaning.

| Scene | Range (ms) | Visual asset | Motion | Subtitle coverage |
|---|---:|---|---|---|
| `scene_001` | 0–3,848 | `scene_001.svg` | 7 object fade-ins; hook | `sentence_001` |
| `scene_002` | 3,848–11,543 | `scene_002.svg` | 5 object fade-ins; payroll and unemployment blocks | `sentence_002`–`sentence_003` |
| `scene_003` | 11,543–18,469 | `scene_003.svg` | 5 object fade-ins; earnings | `sentence_004` |
| `scene_004` | 18,469–24,434 | `scene_004.svg` | 4 object fade-ins; workweek | `sentence_005` |
| `scene_005` | 24,434–30,398 | `scene_005.svg` | 8 object fade-ins; June revision | `sentence_006` |
| `scene_006` | 30,398–35,977 | `scene_006.svg` | 8 object fade-ins; July revision | `sentence_007` |
| `scene_007` | 35,977–45,596 | `scene_007.svg` | 7 object fade-ins; industry comparison | `sentence_008`–`sentence_010` |
| `scene_008` | 45,596–53,484 | `scene_008.svg` | 5 object fade-ins; recap | `sentence_011a` |
| `scene_009` | 53,484–58,679 | `scene_009.svg` | 4 object fade-ins; close | `sentence_011b` |

The composition contains all 9 visual assets and all 12 canonical subtitle cues. It uses the existing subtitle display text and layout; spoken-normalized TTS text is not substituted into captions.

## C. Timing limitation

Alignment method is `proportional_by_normalized_char_count`; timing quality is `estimated`. It is sentence-level proportional timing, **not word-level acoustic alignment**, forced alignment, or WhisperX timing. Subtitle/audio sync must be judged during human preview review.

## D. Exported review MP4

The local review MP4 is:

`D:\Projects\fanglei-economy-content-engine\runs\2026-09-27-001-bls-august-2026-employment-situation\review-preview.mp4`

| Property | Result |
|---|---|
| Purpose | Local human-review preview only; not a final video |
| Size | 3,943,433 bytes |
| SHA-256 | `d846da9f9688887ef7c91fb102fb4341d0f7e6c1f4c9e7fbcbf0b4d6a00fdde7` |
| Duration | 58.700 s container; 58.679 s narration/audio stream |
| Video | H.264, 1080 × 1920, 30 FPS, 1,761 frames |
| Audio | AAC, 48 kHz, stereo |
| Source binding | Current approved Storyboard, Timeline, Candidate 3 visual bundle, subtitle track, and approved narration; their source artifacts were not edited |
| Export method | Existing local HyperFrames 0.8.20 renderer using a temporary wrapper around the existing review composition to supply capture dimensions and timing metadata; no production code or source artifact was changed |

Full video decode and separate audio decode passed. Static samples were inspected at the opening, the midpoint of each of the 9 scenes, and the ending. All 9 scenes appeared and the sampled frames were nonblank. Some subtitle panels overlap lower visual content in scenes 001, 003, and 007; this is recorded for human review and was not changed because this export must preserve the approved composition. Static sampling does not establish perceived playback synchronization.

The renderer reported an interactive `currentTime` control warning for the narration element and no deterministic font mapping for Microsoft YaHei. Sampled scene/caption states rendered, but playback synchronization and typography should be checked by a person. The renderer also logged retrieval/caching of Inter font faces from Google Fonts. No LLM, image-generation, TTS, or external rendering provider was invoked, and the media was not uploaded.

## E. Technical QA

| Check | Result | Evidence / limitation |
|---|---|---|
| Duration | **OK** | MP4 container is 58.700 s; AAC is 58.679 s, matching the approved 58,679 ms audio and Timeline. |
| Video decode | **OK** | Full H.264 video decode passed; 1080 × 1920 at 30 FPS. |
| Audio | **OK** | AAC stream exists; full audio decode passed. Perceived sync still requires human review. |
| Scene coverage | **OK** | 9/9 scene midpoints were sampled from the approved Timeline; all showed nonblank scene content. |
| Subtitle presence | **OK** | Current composition contains all 12 canonical cues. Sampled scene/caption states rendered; timing remains estimated and needs playback review. |
| Subtitle/visual collision | **CAUTION** | Subtitle panels cover or compete with lower visual content in sampled scenes 001, 003, and 007. Preserve this as a human review item; do not treat it as approved. |
| Transition continuity | **OK** | Scene boundaries are contiguous; every generated object-motion cue fits within its scene. |
| Ending completeness | **CAUTION** | Last sampled frame contains scene 009 and is nonblank; perceived audio/video ending sync still requires human inspection. |
| Preview safety | **OK** | MP4 is a local review preview only. Renderer manifest remains `preview_only=true`, `full_render_requested=false`, and `preview_review_status=pending_human_preview_review`; no final render or publication decision was recorded. |
| Rendering warnings | **CAUTION** | HyperFrames reported interactive narration time control and nondeterministic Microsoft YaHei font mapping. Inspect playback and typography on the review machine. |
| Network / provider boundary | **CAUTION** | No LLM, image-generation, TTS, or external rendering provider was used; the renderer logged retrieval/caching of Inter font faces from Google Fonts. No media was uploaded. |

## F. Human Preview Checklist

Open the local HTML preview or play the exported review MP4:

`D:\Projects\fanglei-economy-content-engine\runs\2026-09-27-001-bls-august-2026-employment-situation\renderer_project\review-preview.html`

`D:\Projects\fanglei-economy-content-engine\runs\2026-09-27-001-bls-august-2026-employment-situation\review-preview.mp4`

Review and record a decision for each item:

- [ ] Overall pacing
- [ ] Scene 001 hook speed
- [ ] Scene 002 first data reveal
- [ ] Earnings/workweek pacing
- [ ] June revision comprehension
- [ ] July revision comprehension
- [ ] Industry bar readability
- [ ] Scene 008 recap duration
- [ ] Scene 009 final hold
- [ ] Subtitle/audio synchronization
- [ ] Subtitle/visual collision
- [ ] Footer visibility
- [ ] Any text clipping
- [ ] Animation smoothness
- [ ] Whether motion feels too presentation-like
- [ ] Whether any scene feels too static
- [ ] Audio/video ending synchronization
- [ ] Whether preview is ready for a separate final-render decision

## G. Gate

**HUMAN PREVIEW REVIEW = PENDING**

This packet does not approve a final render, final video, V0.2 completion, or publication. Do not burn in final subtitles, create a final video export, or publish until a separate explicit human decision is recorded.
