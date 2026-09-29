# BLS Case 2 — Timeline Preview Review

**Gate: `HUMAN PREVIEW REVIEW = PENDING`**

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

## D. Technical QA

| Check | Result | Evidence / limitation |
|---|---|---|
| Duration | **OK** | Timeline and preview manifest both bind the approved 58,679 ms audio. |
| Video decode | **CAUTION** | This is a browser-based HTML preview, not an MP4; there is no video stream to decode. No final video was generated. |
| Audio | **OK** | Preview references the local narration WAV and matching approved audio SHA-256. Browser playback was not inspected in this pass. |
| Scene coverage | **OK** | 9/9 scenes mapped to Candidate 3 SVGs; scene ranges are contiguous from 0 through 58,679 ms. |
| Subtitle presence | **OK** | All 12 canonical cues are present, ordered, and within the audio bounds. |
| Transition continuity | **OK** | Scene boundaries are contiguous; every generated object-motion cue fits within its scene. |
| Ending completeness | **CAUTION** | Scene 009 ends with the audio range; visual hold duration and audio/video perceived ending sync require human inspection. |
| Preview safety | **OK** | Renderer manifest sets `preview_only=true`, `full_render_requested=false`, and `preview_review_status=pending_human_preview_review`; HTML shows `PREVIEW · NOT FINAL` and `HUMAN REVIEW REQUIRED`. |
| Visual/browser playback inspection | **CAUTION** | The browser URL policy refused the local `file://` preview. No alternate browser or rendering route was used; clipping, contrast, perceived pacing, and actual playback remain for human review. |

## E. Human Preview Checklist

Open the local preview at:

`D:\Projects\fanglei-economy-content-engine\runs\2026-09-27-001-bls-august-2026-employment-situation\renderer_project\review-preview.html`

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

## F. Gate

**HUMAN PREVIEW REVIEW = PENDING**

This packet does not approve a final render, final video, V0.2 completion, or publication. Do not burn in final subtitles, export MP4, or publish until a separate explicit human decision is recorded.
