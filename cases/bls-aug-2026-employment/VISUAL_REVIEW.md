# BLS August 2026 — Visual Review

**Decision required:** `HUMAN VISUAL REVIEW = PENDING`

This packet is for review of the generated visual assets only. The recovered Storyboard was approved for visual generation; that approval does not approve a Timeline, final subtitle burn-in, or MP4 export.

## Local preview

Open the contact sheet:

`runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets/index.html`

It links to the nine individual SVGs in the same directory. Run artifacts are local and git-ignored, so the preview is available in the working checkout that contains this run.

## Bound inputs

| Item | SHA-256 / identity |
|---|---|
| Run | `2026-09-27-001-bls-august-2026-employment-situation` |
| Case | `bls-aug-2026-employment` |
| Recovered candidate canonical Storyboard | `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded` |
| Candidate file / registry artifact | `920299f4a2e483c5a6aeaeb2afaaa884cdd1a3c04b9c0b1c8d5bd3ca2cc5e7f3` |
| Human approval artifact | `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05` |
| Visual asset directory artifact | `c42d2e93bce4698cacbc1c53a8b8980e61cbd37505c90a87108d9e9373a38b83` |

Approval reviewer: `motty63-ctrl`
Approval time: `2026-09-29T16:43:49+08:00`
Approval scope: generate visuals from the recovered Storyboard while preserving its scene structure, timing, narration segments, supporting claims, and approved display copy.

## Scene inventory

| Scene | Time range | Narration segments | Supporting claims |
|---|---:|---|---|
| `scene_001` | 0–3,848 ms | `sentence_001` | — |
| `scene_002` | 3,848–11,543 ms | `sentence_002`, `sentence_003` | `claim_063`, `claim_064` |
| `scene_003` | 11,543–18,469 ms | `sentence_004` | `claim_065` |
| `scene_004` | 18,469–24,434 ms | `sentence_005` | `claim_066` |
| `scene_005` | 24,434–30,398 ms | `sentence_006` | `claim_067` |
| `scene_006` | 30,398–35,977 ms | `sentence_007` | `claim_068` |
| `scene_007` | 35,977–45,596 ms | `sentence_008`–`sentence_010` | `claim_069`–`claim_071` |
| `scene_008` | 45,596–53,484 ms | `sentence_011a` | `claim_063`–`claim_066` |
| `scene_009` | 53,484–58,679 ms | `sentence_011b` | `claim_067`–`claim_071` |

The visual manifest and SVG hashes were checked against the current candidate. All 9 scene IDs, order, time ranges, narration bindings, claim bindings, and object text match exactly. The SVG bundle is a static typographic treatment of Storyboard objects; it does not add factual copy, claims, causal interpretation, subtitles, or timing behavior.

The displayed scene ranges are inherited from the alignment-derived Storyboard. Its sentence timings use `proportional_by_normalized_char_count` with estimated quality; they are not word-level acoustic alignment.

## Human review checklist

- Confirm each scene communicates the approved Storyboard layout and hierarchy.
- Check text readability, wrapping, spacing, contrast, and screen-edge safety.
- Confirm all figures, signs, labels, and units match the approved display copy.
- Confirm the scene sequence remains coherent across the full contact sheet.
- Flag any visual treatment that could imply an unsupported relationship or conclusion.

## Human decision

Decision: `PENDING`
Reviewer:
Reviewed at (timezone-aware ISO-8601):
Rationale / findings:
