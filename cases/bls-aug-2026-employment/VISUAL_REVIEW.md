# BLS August 2026 — Visual Review

**Current gate: `HUMAN VISUAL REVIEW = PENDING`**

Review Visual Candidate 2 only. Candidate 1 is preserved as `CHANGES_REQUIRED`; its decision does not approve Candidate 2. This review authorizes no Timeline, subtitle burn-in, or MP4 export.

## Local preview

Open the Candidate 2 contact sheet:

`runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets_candidate_2/index.html`

The page labels Candidate 1 `CHANGES_REQUIRED`, Candidate 2 `PENDING HUMAN VISUAL REVIEW`, and shows the nine Candidate 2 SVGs in scene order. Candidate 1 remains separately available at `runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets/index.html`.

## Candidate 1 — formal review record

- Decision: `CHANGES_REQUIRED`
- Reason: `VISUAL_POLISH_AND_MOBILE_HIERARCHY`
- Reviewer: `motty63-ctrl`
- Reviewed at: `2026-09-29T17:51:15+08:00`
- Review artifact SHA-256: `4a326d5ccd1b1614f2e9689fcd789d7033c2219260b65ba66f09ba2691074744`
- Original visual bundle SHA-256: `c42d2e93bce4698cacbc1c53a8b8980e61cbd37505c90a87108d9e9373a38b83`

Human findings: the nine assets were factually and structurally correct, and the dark visual system was acceptable, but the sequence felt too much like data slides. Several scenes needed stronger mobile hierarchy, larger primary values, and more intentional use of space. Scenes 5–6 should form a clearer revision climax; Scene 7 should express magnitude and direction; Scenes 8–9 should feel less like consecutive report pages. The BLS footer should remain small and consistent. No upstream factual or content change was requested.

## Candidate 2 — pending human review

| Item | SHA-256 / identity |
|---|---|
| Run / case | `2026-09-27-001-bls-august-2026-employment-situation` / `bls-aug-2026-employment` |
| Candidate | `2`; manifest status `pending_human_visual_review` |
| Recovery-plan registry artifact | `ca122df2b49aa41c7edce6944278d49d208da2ab4d662244f54c249cad94e3f1` |
| Canonical recovery-plan digest | `8f9c8f0764a129ebbefeb1d44eafee65e1b688710b404675cd0c989db32c080a` |
| Candidate 2 visual bundle | `2b8034e9dfcaaf1330077e1a3403442cdca7232242dc9518214bde6dbfa35d2c` |
| Candidate 1 review bound into recovery | `4a326d5ccd1b1614f2e9689fcd789d7033c2219260b65ba66f09ba2691074744` |
| Recovered Storyboard canonical SHA-256 | `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded` |
| Storyboard approval SHA-256 | `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05` |
| Script SHA-256 | `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` |
| Approved audio Candidate 2 SHA-256 | `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183` |
| Alignment SHA-256 | `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306` |
| Subtitle track SHA-256 | `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46` |

The Storyboard SHA, nine scene IDs and order, exact `0–58,679 ms` timing, 12/12 narration-segment ownership, supporting claims, and approved display copy are unchanged. Candidate 2 changes visual composition only. It contains nine SVGs plus a manifest and local contact sheet. The source footer is `Source: BLS` from Scene 2 onward; Scene 1 omits it.

The alignment remains `proportional_by_normalized_char_count` with estimated quality, not word-level acoustic alignment. Candidate 2 is a static visual-asset review set, not a Timeline or video.

## Candidate 2 scene treatment

| Scene | Visual treatment to review |
|---|---|
| `scene_001` | Opening hook `别只盯一个数字` as the focal point, with six lower-hierarchy report dimensions arranged around it. |
| `scene_002` | Two separated metric cards for nonfarm payroll and unemployment, with values prominent and the unchanged status subordinate. |
| `scene_003` | Earnings metric card dominated by `37.75美元`, with `+10美分` and `+0.3%` as secondary chips and private nonfarm scope subordinate. |
| `scene_004` | Workweek value `34.4小时` with `+0.1小时`; a simple clock/tick geometry differentiates it from the earnings scene. |
| `scene_005` | June revision shown as prior `+2万` to revised `+3.1万`; `上修 +1.1万` is visually separate from the revised value. |
| `scene_006` | July revision shown as `−2.3万` to `+2.1万`, emphasizing the sign change; `上修 +4.4万` remains a separate revision badge. |
| `scene_007` | `部分行业变化` with diverging magnitude bars for two positive movements and one negative movement, without ranking or implying an exhaustive list. |
| `scene_008` | A four-tile structural recap grouping August's current payroll, unemployment, earnings, and workweek measures without repeating values. |
| `scene_009` | Closing phrase `这些信息需要分开看` with three organized categories: August current indicators, June/July revisions, and selected industry changes. |

## Static QA note for reviewer

The SVGs and manifest passed structural/hash validation, and all displayed strings remain bound to the approved visual objects. A static SVG text-line inspection found that the renderer wrapped some numeric strings at arbitrary character boundaries: `+16.2万` in Scene 2 and several revision magnitudes in Scenes 5–7 split the number from `万`. Some longer labels also wrap. No text or value was changed, and this was not raster/browser visual QA. Please inspect these wraps at phone size and decide whether they are readable enough for this candidate. **Do not treat static/hash validation as proof of visual readability.** If the wrapping is not acceptable, record `CHANGES_REQUIRED`; do not approve Candidate 2 or proceed downstream.

## Human review checklist

1. Hook hierarchy in Scene 1.
2. Numeric prominence in Scene 2.
3. Earnings-value readability in Scene 3.
4. Workweek differentiation in Scene 4.
5. June revision clarity in Scene 5.
6. July sign-flip clarity in Scene 6.
7. Industry magnitude visualization in Scene 7.
8. Structural recap in Scene 8.
9. Final-card quality in Scene 9.
10. Consistency of the source footer.
11. Font size and readability on a mobile screen.
12. Safe distance from screen edges and player controls.
13. Whether empty space feels intentional.
14. Visual rhythm across all nine scenes.
15. Whether the sequence still feels like slides rather than video keyframes.

## Human decision — Candidate 2

Decision: `PENDING`

Reviewer:

Reviewed at (timezone-aware ISO-8601):

Rationale / findings:
