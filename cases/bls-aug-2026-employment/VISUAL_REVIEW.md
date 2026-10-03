# BLS August 2026 — Visual Review

**Current gate: `HUMAN VISUAL REVIEW = PENDING`**

Review Visual Candidate 3 only. Candidate 1 and Candidate 2 are preserved with their formal `CHANGES_REQUIRED` decisions; neither decision approves Candidate 3. This review authorizes no Timeline, subtitle burn-in, or MP4 export.

## Local preview

Open the Candidate 3 contact sheet:

`runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets_candidate_3/index.html`

The page links Candidate 2 as `CHANGES_REQUIRED`, labels Candidate 3 `PENDING HUMAN VISUAL REVIEW`, and shows all nine Candidate 3 SVGs in scene order. Candidate 1 and Candidate 2 previews remain separately available in their own directories.

## Candidate 1 — formal review record

- Decision: `CHANGES_REQUIRED`
- Reason: `VISUAL_POLISH_AND_MOBILE_HIERARCHY`
- Reviewer: `motty63-ctrl`
- Reviewed at: `2026-09-29T17:51:15+08:00`
- Review artifact SHA-256: `4a326d5ccd1b1614f2e9689fcd789d7033c2219260b65ba66f09ba2691074744`
- Original visual bundle SHA-256: `c42d2e93bce4698cacbc1c53a8b8980e61cbd37505c90a87108d9e9373a38b83`

Human findings: the nine assets were factually and structurally correct, and the dark visual system was acceptable, but the sequence felt too much like data slides. Several scenes needed stronger mobile hierarchy, larger primary values, and more intentional use of space. Scenes 5–6 should form a clearer revision climax; Scene 7 should express magnitude and direction; Scenes 8–9 should feel less like consecutive report pages. The BLS footer should remain small and consistent. No upstream factual or content change was requested.

## Candidate 2 — formal review record

| Item | SHA-256 / identity |
|---|---|
| Run / case | `2026-09-27-001-bls-august-2026-employment-situation` / `bls-aug-2026-employment` |
| Candidate | `2`; human decision `CHANGES_REQUIRED` |
| Recovery-plan registry artifact | `ca122df2b49aa41c7edce6944278d49d208da2ab4d662244f54c249cad94e3f1` |
| Canonical recovery-plan digest | `8f9c8f0764a129ebbefeb1d44eafee65e1b688710b404675cd0c989db32c080a` |
| Candidate 2 visual bundle | `2b8034e9dfcaaf1330077e1a3403442cdca7232242dc9518214bde6dbfa35d2c` |
| Candidate 2 review | `cc5fde5310560a213ff237b5e6ee150b243aabf8ca204bce8070e17d55d036c6` at `2026-09-29T19:26:39+08:00` |
| Candidate 1 review bound into recovery | `4a326d5ccd1b1614f2e9689fcd789d7033c2219260b65ba66f09ba2691074744` |
| Recovered Storyboard canonical SHA-256 | `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded` |
| Storyboard approval SHA-256 | `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05` |
| Script SHA-256 | `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` |
| Approved audio Candidate 2 SHA-256 | `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183` |
| Alignment SHA-256 | `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306` |
| Subtitle track SHA-256 | `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46` |

Reviewer `motty63-ctrl` recorded `CHANGES_REQUIRED / NUMERIC_WRAP_AND_LABEL_READABILITY`. The hierarchy was broadly acceptable; no Storyboard redesign, color change, or visual-identity change was requested. The blocking findings were numeric value/unit wrapping, long-label readability, and mobile safe-area consistency. The source footer and the direction of Scenes 005/006 and 008/009 were accepted.

The Storyboard SHA, nine scene IDs and order, exact `0–58,679 ms` timing, 12/12 narration-segment ownership, supporting claims, and approved display copy remained unchanged. Candidate 2 contains nine SVGs plus a manifest and local contact sheet. Its source footer is `Source: BLS` from Scene 2 onward; Scene 1 omits it.

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

## Candidate 2 static QA history

The SVGs and manifest passed structural/hash validation, but static SVG text inspection found number/unit wraps and long-label readability issues. The reviewer confirmed these required a layout-only recovery. This finding is historical; Candidate 3 has a distinct bundle, and its static checks still do not replace the final human mobile readability review.

## Candidate 3 — pending final human visual review

| Item | SHA-256 / identity |
|---|---|
| Candidate | `3`; manifest status `pending_human_visual_review` |
| Candidate 3 visual bundle | `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355` |
| Candidate 3 recovery plan artifact | `8229cb06c3e10a806a8ed5e0343d3b138e7ed26bc376d01462537bf8d479ff66` |
| Candidate 2 review bound as source | `cc5fde5310560a213ff237b5e6ee150b243aabf8ca204bce8070e17d55d036c6` |
| Recovered Storyboard canonical SHA-256 | `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded` |
| Script / audio / alignment / subtitle | unchanged; hashes remain listed in the Candidate 2 table above |

Candidate 3 is a separate nine-SVG bundle generated from the same approved recovered Storyboard. Storyboard, Script, audio, alignment, subtitle track, selected angle, eligible claims, scene count/IDs/order/timing, narration coverage, factual display copy, and visual concepts are unchanged. Only mobile layout/readability was refined. Candidate 1 and Candidate 2 review identities and bundles remain preserved.

Static validation confirms all nine SVGs parse with the expected `1080×1920` canvas and original scene order/timing; each number object renders its exact value and unit in one line. Scene 7 labels use the plan's explicit line-break hints. `Source: BLS` remains small and inside the checked safe region from Scene 2 onward. These checks verify structure and text placement, not perceived readability on every device.

## Candidate 3 human checklist

Inspect only these final mobile-layout points:

1. `+16.2万` remains intact.
2. June values and units remain intact.
3. July values and units remain intact.
4. Industry values remain intact.
5. Long industry labels wrap naturally.
6. No standalone orphan `万` appears.
7. Currency and time units stay with their values.
8. Primary numbers remain large enough.
9. All critical content stays inside safe margins.
10. The source footer remains unobtrusive.
11. No text is clipped.
12. The nine-scene rhythm is unchanged.

## Human decision — Candidate 3

Decision: `PENDING`

Reviewer:

Reviewed at (timezone-aware ISO-8601):

Rationale / findings:

No Timeline, animation, final subtitle burn-in, or MP4 has been generated. Do not proceed until a separate explicit human visual decision is recorded for Candidate 3.
