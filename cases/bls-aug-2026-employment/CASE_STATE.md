# BLS August 2026 Employment Situation — Case State

## Identity and current status

- Case ID: `bls-aug-2026-employment`
- Run ID: `2026-09-27-001-bls-august-2026-employment-situation`
- Status: **`V0.2_PHASE_3C5C_WAITING_FOR_PREVIEW_REVIEW`**. Preview Candidate 1: human `CHANGES_REQUIRED`; Preview Candidate 2: technical render failure, not human-reviewed; Preview Candidate 3: current/valid, awaiting human review. Visual Candidate 3 remains approved. No final-render approval or final MP4 exists.
- Target: BLS Employment Situation — August 2026.
- Comparison source: BLS Employment Situation — July 2026 archive.
- Five BLS angle candidates were generated and `angle_001` was explicitly selected. The Script received explicit human approval for TTS and remains unchanged. Audio Candidate 1's formal rejection and media are archived; audio Candidate 2 is human-approved for Storyboard. See [AUDIO_REVIEW.md](AUDIO_REVIEW.md). Alignment and subtitles remain current. The original 9-scene Storyboard was reviewed as `CHANGES_REQUIRED`; its recovered candidate was approved for visual generation. Visual Candidates 1 and 2 are formally `CHANGES_REQUIRED`; Candidate 3 is approved for Timeline. See [VISUAL_REVIEW.md](VISUAL_REVIEW.md) for preserved candidate history and [PREVIEW_REVIEW.md](PREVIEW_REVIEW.md) for the current review packet. No final MP4 exists for this BLS run.

## Locked research question

2026 年 8 月美国就业报告中，非农就业、失业率、工资和工时发生了什么变化？6 月与 7 月非农就业数据被如何修正，哪些行业对 8 月就业变化贡献较大或形成拖累？

The case asks what the BLS documents report. It does not ask for causes, Federal Reserve policy effects, recession or soft-landing conclusions, market effects, political implications, or future rate implications. Household-survey unemployment must remain distinct from establishment-survey payroll employment, earnings, and hours.

## Approved source package and capture state

| Source | Exact URL | Reviewed publication date | Normalized text SHA-256 | Raw capture hash |
|---|---|---:|---|---|
| `src_001` — Employment Situation, August 2026 | <https://www.bls.gov/news.release/empsit.htm> | `2026-09-04` | `4a4491e19010fb560aefdccd072463ad400b51d628a1a7df60ba3d75ff2db121` | `null` |
| `src_002` — Employment Situation, July 2026 archive | <https://www.bls.gov/news.release/archives/empsit_08072026.htm> | `2026-08-07` | `8e43fdb02dae6381dbf793f3e37789a69aa0cef9864ede493175e3b416ab4e07` | `null` |

Both publication dates were approved by `motty63-ctrl` at `2026-09-27T20:04:42+08:00`, bound to the exact normalized-text hashes and release-header excerpts. The `authoritative_primary_set/1.0` package was approved by the same reviewer at that time. Package SHA-256 is `13680d96d487497ed19d95ecbd09ccbf213e732f6787dc066320e11ed44355d9`. The approval covers only these source documents and their evidence roles; it does not approve future claims or causal, motive, or market-impact interpretations.

The Phase 3A.1 reprocessing did not change either capture, source ID, URL, publication review, source row, or approved package. `source_documents/index.json` and `sources.json` remain registry-valid/current; `fetch_errors` is empty, independent source count remains `1`, and legacy `selection_status` remains `insufficient_sources`.

## Historical initial Phase 3A checkpoint

The first Phase 3A factcheck correctly stopped at `PHASE_3A_BLOCKED_GENERALIZATION_GAP`. That snapshot contained 62 facts (7 verified, 1 conflicted, 54 unverified) and did not provide complete eligible evidence for earnings, workweek, and line-wrapped revision values. This is retained as a historical checkpoint; its partial `facts.json` and Research output have been superseded through the formal owners and must not be restored over the current run.

## Phase 3A.1/3A.2 extraction contract and current Facts

The run-bound `evidence_targets.json` is case configuration: it declares concepts, retrieval aliases, periods, approved source roles, expected unit families, authority scope, and where required the exact source section. It contains no asserted metric values. Values are extracted only from the approved local captures.

Generic narrative locators use `line:N`, `line:N-M`, or `line:N-M;columns:S-E`. Column offsets are zero-based Python Unicode-code-point offsets into the newline-joined physical line range. The authority verifier reconstructs the exact excerpt from the capture before accepting it. Narrative evidence can also bind its nearest explicit section heading with a separate line locator; the BLS unemployment claim is bound to `Household Survey Data`, while payroll, earnings, workweek, revisions, and industry claims bind to `Establishment Survey Data` or the document's overview heading. Generic table candidates preserve table identity, row path, column-header path, period, explicit unit/statistic, and cell/header locators.

The generic table parser produced 3,824 structured cell candidates from each of the two current BLS captures. Targeted verified claims below use exact attributed narrative evidence and are independently checked against their source locators and section context.

Current native `facts.json` is schema `2.2`: **71 claims total — 9 verified, 1 conflicted, and 61 unverified**. The nine verified target claims are all `authoritative_primary_attestation` with `allowed_downstream=true`:

| Claim | Verified content | Source | Evidence locator | Bound source section |
|---|---|---|---|---|
| `claim_063` | August nonfarm payroll employment increased by 162,000 | `src_001` | `line:44-45;columns:0-172` | `THE EMPLOYMENT SITUATION - AUGUST 2026` |
| `claim_064` | August unemployment rate unchanged at 4.1 percent | `src_001` | `line:54-55;columns:0-128` | `Household Survey Data` |
| `claim_065` | Average hourly earnings rose by 10 cents / 0.3 percent to $37.75 | `src_001` | `line:108-109;columns:0-125` | `Establishment Survey Data` |
| `claim_066` | Average workweek edged up by 0.1 hour to 34.4 hours | `src_001` | `line:112-113;columns:0-112` | `Establishment Survey Data` |
| `claim_067` | June estimate revised up by 11,000, from +20,000 to +31,000 | `src_001` | `line:117-118` | `Establishment Survey Data` |
| `claim_068` | July estimate revised up by 44,000, from -23,000 to +21,000 | `src_001` | `line:117-118` | `Establishment Survey Data` |
| `claim_069` | Food services and drinking places employment increased by 59,000 | `src_001` | `line:87-88` | `Establishment Survey Data` |
| `claim_070` | Local government education added 42,000 jobs | `src_001` | `line:89-90;columns:0-105` | `Establishment Survey Data` |
| `claim_071` | Information employment declined by 23,000 | `src_001` | `line:97-98;columns:0-129` | `Establishment Survey Data` |

The June and July revision claims use the same source sentence, but each target binds its own period and the corresponding explicit previous/revised values. This is one BLS institution and one source document; no independent-source count is added. No verified claim currently uses `src_002` for an additional cross-document comparison with the values printed in the July release; such a comparison must remain unasserted unless separately extracted and verified.

## Phase 3A.2 atomic claim and authority-scope alignment

For run-bound targeted narrative evidence, `evidence_text` remains the full exact source span used for provenance. The optional `proposition_span` records exact Python Unicode-code-point offsets and text for the single proposition used by the claim. The authority verifier requires that span to match a deterministic atom reconstructed from the capture, and requires the attested scope to exactly match the registered target scope. A composite candidate cannot become `verified` or `allowed_downstream` merely because one clause matches its scope.

The BLS run was reprocessed offline through the formal factcheck and deterministic Research owners. `claim_063` now contains only the payroll proposition; `claim_064` contains only the unemployment-rate proposition; `claim_067` and `claim_068` separately contain the June and July revision propositions; and `claim_069`–`claim_071` contain only the current-month industry movements. The historical-average and prior-month-offset clauses remain in the full evidence spans but are not emitted as claim or Research content. Explicit units found in source text remain in structured `explicit_values`; no unit is inferred when the text does not state one.

Research renders the same atomic proposition used by each verified claim and retains BLS attribution, source ID, and locator. Household-survey unemployment remains separate from establishment-survey payroll, earnings, hours, revisions, and industry claims. Industry coverage is partial: the current eligible evidence names two increasing industries and one declining industry; it is not a complete ranking of all industry changes. Current Research has 9 eligible findings; no unverified or conflicted claim enters it.

Current Facts SHA-256: `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`. Current Research SHA-256: `ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862`. The run artifacts are local under ignored `runs/`; this record does not imply they are tracked in Git. The rerun used fail-on-call search/fetch stubs; both call counts were zero. Sources, source index, captures, publication reviews, and approved package were unchanged. At the Phase 3A.2 reprocessing checkpoint, no Angle or later content artifact had yet been generated.

Historical review status: **`PHASE_3A_HUMAN_REVIEW_READY`** was the state before the approval recorded in `PHASE3A_APPROVAL.json`. That record binds the reviewed Facts, Research, Research Focus, Sources, and source index hashes and authorizes Angle Planning only; it does not authorize angle selection or later content stages.

## Current deterministic Research

`research_focus.json` and `research.md` are registry-valid/current. Research references exactly `claim_063` through `claim_071`; each is verified and allowed downstream. It preserves the household/establishment survey distinction, reports the June and July revision values from the August release, and shows several explicitly described industry increases and declines. It does not infer causes or combine survey measures. The remaining 62 records are excluded from substantive findings because they are unverified or not allowed downstream.

The reprocessing used only local artifacts. Search and fetch providers were replaced with fail-on-call stubs and were not called. Sources and normalized captures were not rewritten. No facts, source approvals, or case input values were manually inserted into the run artifacts.

## Historical Phase 3A verification

Phase 3A.1 extraction-focused tests: 88 passed; Phase 3A.2 focused extraction/authority/Research/pipeline tests: 90 passed; Phase 3A.2 safe non-integration regression: 729 passed. `git diff --check` passed.

## Historical Phase 3B.1 angle review (superseded)

The generic atomic-authority safety fix is committed at `a0ecb8be28ac911ecff3741a6330fa8d8339d828`. It treats the verified `proposition_span` as the factual unit for atomic V0.2 claims while retaining the complete evidence text as provenance; unsupported neighboring clauses remain ineligible unless backed by their own verified atomic claim.

The formal offline Angle Planning owner generated five eligible candidates in `runs/2026-09-27-001-bls-august-2026-employment-situation/angles.json`, SHA-256 `b897f1eaca70ce4bd3b7482fd9304ecead3e1eb9930609c4ea39467bdbc70afb`. All five supported only their listed verified claims and passed the authority-safety check. That review packet was superseded by Phase 3B.2; the historical hash is retained as evidence of the earlier candidate set.

## Historical Phase 3B.2 generic angle coverage and editorial quality

The canonical offline angle-generation owner regenerated five candidates after the generic coverage and editorial-quality update. Current `angles.json` SHA-256 is `32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8`. All five are `eligible`, have no rejection codes, pass the authority-safety check, pass the editorial-quality check, and pass candidate-set diversity. The system recommendation is `angle_001` with score 87; it is not a human choice.

The candidate set uses all nine eligible claims (`claim_063`–`claim_071`). Four of five Research Focus dimensions have supporting claims: payroll/unemployment, earnings/workweek, June/July revisions, and selected industry changes. The survey-boundary dimension has no directly eligible supporting claim and remains explicitly omitted. Industry coverage remains partial: two named increases and one decline, not a complete ranking. The review packet is [ANGLE_REVIEW.md](ANGLE_REVIEW.md).

The five-candidate review resulted in a human selection of `angle_001`; see the current selection record below. This section retains the prior recommendation and coverage snapshot as phase history.

## Historical Phase 3C.1.3 — terminology approved; Script attempt was next

The selected angle is `angle_001`. Facts, Research Focus, Research, `angles.json`, and `angle_selection.json` remain current and unchanged. Their recorded SHA-256 values are Facts `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`, Focus `fe638d26622e271951365188f9fe0ba0b474ee2fb3bde3c544e0e91f4098b32a`, Research `ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862`, Angles `32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8`, and selection `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77`.

Phase 3C.1 and 3C.1.1 are retained as historical blocked checkpoints: English authoritative claims could not safely validate Chinese narration through literal proposition matching. Phase 3C.1.2 adds a generic, Facts-hash-bound `script-terminology-map/1.0` contract, cross-language validation foundations, structured numeric/revision/scope checks, bounded attribution context, duration-target quality, repair editability, and generic closing checks. Phase 3C.1.3 records the human decisions through the formal owner; it does not change Facts, Research, the selected angle, or terminology trust rules.

The 46-entry review in [TERMINOLOGY_REVIEW.md](TERMINOLOGY_REVIEW.md) records **40 APPROVED / 6 REJECTED_AS_NON_TERMINOLOGY / 0 PENDING**. Reviewer `motty63-ctrl` recorded the decisions at `2026-09-28T14:57:47+08:00`. The formal map at `runs/2026-09-27-001-bls-august-2026-employment-situation/script_terminology.json` is bound to case `bls-aug-2026-employment`, this run, and Facts SHA-256 `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`; its artifact SHA-256 is `a9ee561650535b58d3c6f5bb36c30a884225f70c202f6f0923e2954f05262d2c`. The corrected `term_a8efeac80fd5` decision maps `change` (metric; `claim_067`, `claim_068`) to `变动`, with approved alias `变化`. The six numeric entries are excluded from the trusted terminology map and remain represented by structured Facts fields.

At that checkpoint, terminology/selection/script-quality focused validation passed **103 tests** and the safe non-integration regression passed **796 tests**. The checks used offline/local fixtures. The next action recorded then was superseded by the human-script recovery below.

## Historical Phase 3C.1.5 — human-edited Script candidate before approval

The formal `submit_human_script_recovery(...)` owner accepted the exact human-provided Chinese candidate, after only structurally splitting its final long sentence into two adjacent segments whose concatenation preserves the supplied wording. The owner validated upstream artifact freshness, selected-angle identity, approved terminology, claim bindings, and the full script lint before writing any output. The edit is recorded in `runs/2026-09-27-001-bls-august-2026-employment-situation/human_script_edit.json`; rendered artifacts are `script.json` and `script.md`. No Facts, Research, angle, source package, or terminology decision was changed, and no provider was called.

The candidate references `claim_063`–`claim_071`, passes script lint, and has an estimated duration of **65.0 seconds** against a 75-second editorial target. The only lint finding is the non-blocking `DURATION_TARGET_MISSED` warning; the estimate remains within the configured 60–90 second hard range. The candidate's canonical draft SHA-256 is `2d27970c364bf2066896973b6e6322d89b4c35c55bbface7cd23dc78ba47aa75`; `script.json` SHA-256 is `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305`. The review packet is [SCRIPT_REVIEW.md](SCRIPT_REVIEW.md).

The human edit and rendered Script are registered/current against the existing Facts, Research, angle selection, and terminology artifacts. `script.json` records `human_review_status=pending`; lint success is not script approval. **Exact next action: human review of `SCRIPT_REVIEW.md` and the candidate Script.** Do not call TTS, create audio approval, storyboard, timeline, or video until a separate explicit authorization is provided.


## Historical Phase 3C.2A — Audio Candidate 1

The human-approved Script remains unchanged at SHA-256 `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305`; its formal `approved_for_tts` record is SHA-256 `8653415689546d56295f857722840de61f14d26515d836f077a1a13818e3c59f`. The canonical `narration.json` and `narration.txt` remain current and unchanged. One production TTS request to the configured Volcengine endpoint succeeded after the prior local Windows socket-permission failure was diagnosed; no provider request ID was returned or recorded.

The combined audio is `runs/2026-09-27-001-bls-august-2026-employment-situation/audio/narration.wav`, SHA-256 `54b112a49a3e9d8dba484067ee2deaffa3aa043cb20ea0c9e58546a0b0a9af6a`, 2,949,538 bytes, mono PCM 16-bit WAV at 24 kHz, measured duration 61.448 seconds. The technical quality artifact passed its existing checks. The narration contains 12 canonical segments submitted in order in one combined request; the provider supplied no per-segment timing. The duration is about 3.552 seconds shorter than the Script estimate of 65.0 seconds. This is a listening caution, not a reason to edit or time-stretch the approved Script/audio.

[AUDIO_REVIEW.md](AUDIO_REVIEW.md) retains the first candidate's request details. Human review later recorded `CHANGES_REQUIRED / NUMERIC_PRONUNCIATION`; its WAV, metadata, quality, and formal review are preserved under `runs/2026-09-27-001-bls-august-2026-employment-situation/artifacts/audit/audio-candidate-1/`. Candidate 1 is not approved for downstream use.

## Historical Phase 3C.2B — Audio Candidate 2 generated

The generic zh-CN spoken-number normalization implementation is committed at `8563f280581b548596126bff41507c65c685be3c`. It keeps Script/display text unchanged and creates auditable provider-bound spoken text; the code contains no BLS- or value-specific production branch. Focused tests passed **97**; safe non-integration regression passed **858**.

One authorized Volcengine `volcengine-v3-sse` request generated the canonical WAV with the same approved Script, voice, language, rate, pitch, and volume. Candidate 2 SHA-256 is `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183`; it is mono PCM16 WAV at 24 kHz, 2,816,628 bytes, duration 58.679 seconds. Registry/hash validation and the existing production audio-quality gate pass. The Script SHA (`450c61b…d84305`) and Human Script Approval SHA (`86534156…e3c59f`) were unchanged. This section records the state before the subsequent human approval.

## Historical Phase 3C.3 — audio approved; initial Storyboard contract blocked

Reviewer `motty63-ctrl` approved Candidate 2 for Storyboard at `2026-09-29T12:45:14+08:00`. The formal registered review is `runs/2026-09-27-001-bls-august-2026-employment-situation/audio/review.json` (SHA-256 `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f`) and is bound to the current Script SHA `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` and Candidate 2 audio SHA `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183`.

The existing local `run_proportional_sentence_timing(...)` owner produced `alignment.json` (SHA-256 `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306`). It covers all 12 canonical narration segments from 0 to 58,679 ms using proportional character-count estimates, with no missing IDs, overlap, or out-of-bounds timing. This is estimated sentence timing, not acoustic alignment. The existing subtitle owner produced `subtitle_track.json` (SHA-256 `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46`) with 12 cues whose text matches the canonical Script/display text; TTS spoken-normalized text is excluded. Both artifacts and their dependency hashes are current.

At that historical checkpoint, status was `PHASE_3C3_BLOCKED_GENERALIZATION_GAP`: the generic Storyboard path did not consume the approved audio, alignment, or subtitle artifacts. `run_visual_pipeline()` sent only run ID, Script, and allowed claim IDs to the beat planner; its registered Storyboard dependencies were `visual_beats.json`, `script.json`, and `facts.json`. The schema recorded estimated speech duration and relative scene windows, not audio-bound scene timing or subtitle links. It also did not pass selected-angle and approved research-framing artifacts as Storyboard inputs. This blocker was resolved by later generic Phase 3C.3 work recorded below.

That checkpoint's next action was to generalize the Storyboard request/owner and artifact dependencies. It is superseded by the current state below.

## Historical Phase 3C.3C — original timing-aware Storyboard and renderer correction

The generic `render_visual_plan()` renderer now branches on Storyboard timing semantics. Legacy schema 4.0 / `estimated_speech` output retains its original no-audio-timestamp explanation. Alignment-derived Storyboard output shows its timing basis, source, method, estimated quality, audio binding, and scene `start_ms` / `end_ms` / duration directly from the Storyboard, with an explicit precision caveat. The existing Storyboard was not regenerated: its SHA-256 remains `a649b81656193ffbac7898361d9c6b7227b9bd2411cf1208756c1b1e6b85e9e6`; it remains schema 5.0 with 9 scenes, all 12 narration segments, `0–58,679 ms`, and automated quality gate passed.

The corrected `visual_plan.md` is rendered through the `visual_plan_render` ArtifactRegistry owner from the existing Storyboard. Planner/storyboard stage attempt counts remain unchanged; no provider or network was called. Focused visual/rendering tests passed 38; the safe non-integration regression passed 879. The generic renderer fix is committed at `356a0c3` (`fix: render timing-aware visual plan provenance`).

The original review packet recorded the first candidate and its automated checks. Human review later returned `CHANGES_REQUIRED / VISUAL_DIFFERENTIATION_AND_HIERARCHY`; that packet is superseded by the current Phase 3C.3D review packet below. No visual asset production, Timeline, or MP4 rendering started in Phase 3C.3C.

## Historical Phase 3C.3D — human-edited Storyboard candidate

The original Storyboard SHA-256 `a649b81656193ffbac7898361d9c6b7227b9bd2411cf1208756c1b1e6b85e9e6` remains preserved with the registered human decision `CHANGES_REQUIRED`, reason `VISUAL_DIFFERENTIATION_AND_HIERARCHY`. No generic human Storyboard recovery mechanism existed before this phase. A generic recovery owner now records a human visual edit and a separate candidate, validates visual-only changes against the frozen scene/timing/claim contract, and renders `visual_plan.md` from that candidate.

The edit is recorded at `runs/2026-09-27-001-bls-august-2026-employment-situation/human_storyboard_edit.json` (SHA-256 `134150cab8ef623d28fc41427f1566755b5caf157f87cf39a6a67ee2906f8313`); its pending candidate's canonical Storyboard SHA-256 is `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`, and candidate file/registry SHA-256 is `920299f4a2e483c5a6aeaeb2afaaa884cdd1a3c04b9c0b1c8d5bd3ca2cc5e7f3`. The separate original-review record SHA-256 is `4440e5aafda16c36b4217795a07abdb651c36901c2df006dfe183d4bb2ebfe6b`. Reviewer `motty63-ctrl` submitted the edit at `2026-09-29T15:42:57+08:00`; the candidate remains `pending_human_review`.

All 9 original scene IDs, scene order, exact timing (`0–58,679 ms`), and 12/12 narration segment ownership remain unchanged. The common recovery validator and Storyboard quality gate pass. Timing remains alignment-derived, `proportional_by_normalized_char_count`, quality `estimated`; it is not word-level acoustic alignment. Facts, Research, angle, Script, audio, alignment, and subtitles were not changed. Focused recovery tests: 13 passed; focused recovery/visual pipeline/renderer/model suite: 24 passed; safe non-integration regression: 892 passed. No external provider was called.

This Storyboard-review waiting state was superseded when the human approved the recovered candidate for visual generation in Phase 3C.4. See the current gate below.

## Historical Phase 3C.4 — Visual Candidate 1

Reviewer `motty63-ctrl` approved the recovered candidate for visual generation at `2026-09-29T16:43:49+08:00`. The formal `human_storyboard_approval.json` SHA-256 is `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05`. It binds case `bls-aug-2026-employment`, run `2026-09-27-001-bls-august-2026-employment-situation`, the recovered Storyboard canonical SHA-256 `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`, candidate artifact SHA-256 `920299f4a2e483c5a6aeaeb2afaaa884cdd1a3c04b9c0b1c8d5bd3ca2cc5e7f3`, and 16 current upstream artifact hashes. The original Storyboard and its changes-required decision remain unchanged.

The deterministic offline owner generated nine SVG scene assets, `manifest.json`, and a local `index.html` contact sheet under `runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets/`. The original visual bundle SHA-256 is `c42d2e93bce4698cacbc1c53a8b8980e61cbd37505c90a87108d9e9373a38b83`. Reviewer `motty63-ctrl` formally recorded `CHANGES_REQUIRED / VISUAL_POLISH_AND_MOBILE_HIERARCHY` at `2026-09-29T17:51:15+08:00`; review artifact SHA-256 is `4a326d5ccd1b1614f2e9689fcd789d7033c2219260b65ba66f09ba2691074744`. Candidate 1 remains preserved as historical evidence and was not overwritten.

## Historical Phase 3C.4A — visual-only asset recovery

The generic recovery owner accepted a run-bound plan and generated Visual Candidate 2 in `runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets_candidate_2/`. The recovery-plan registry artifact SHA-256 is `ca122df2b49aa41c7edce6944278d49d208da2ab4d662244f54c249cad94e3f1`; its canonical plan digest is `8f9c8f0764a129ebbefeb1d44eafee65e1b688710b404675cd0c989db32c080a`. Candidate 2 bundle SHA-256 is `2b8034e9dfcaaf1330077e1a3403442cdca7232242dc9518214bde6dbfa35d2c`. Reviewer `motty63-ctrl` recorded `CHANGES_REQUIRED / NUMERIC_WRAP_AND_LABEL_READABILITY` at `2026-09-29T19:26:39+08:00`; review SHA-256 is `cc5fde5310560a213ff237b5e6ee150b243aabf8ca204bce8070e17d55d036c6`.

The recovered Storyboard canonical SHA-256 remained `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`. Candidate 2 retained all nine scene IDs/order, the exact `0–58,679 ms` timeline, 12/12 narration-segment coverage, claim bindings, and approved display copy. Static SVG text inspection flagged number/unit wrapping and long-label readability issues; no readability approval was implied.

## Historical Phase 3C.4B — mobile text layout finalization

The Candidate 2 decision was recorded through the generic candidate-specific human review owner. A new layout-only recovery plan produced Candidate 3 at `runs/2026-09-27-001-bls-august-2026-employment-situation/visual_assets_candidate_3/`. Candidate 3 bundle SHA-256 is `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355`; recovery-plan artifact SHA-256 is `8229cb06c3e10a806a8ed5e0343d3b138e7ed26bc376d01462537bf8d479ff66`. Its contact sheet is `visual_assets_candidate_3/index.html`.

Candidate 3 remains bound to the same recovered Storyboard SHA-256 `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`, with the same nine scenes, IDs/order, `0–58,679 ms` timing, narration coverage, claim bindings, approved copy, Script, audio, alignment, and subtitle track. Only numeric value/unit wrapping, label line breaks, and mobile layout bounds were refined. All nine SVGs and manifest validate; numeric value-unit tokens render on one line; `Source: BLS` remains unobtrusive and inside the checked safe area from Scene 2 onward.

At the Phase 3C.4B checkpoint, Candidate 3 was awaiting its final visual decision. That gate was later resolved by the explicit, hash-bound approval recorded in Phase 3C.5 below; the prior Candidate 1/2 decisions and bundles remain preserved.

## Historical Phase 3C.5 — approved visual, Timeline, motion, and preview

Reviewer `motty63-ctrl` approved Visual Candidate 3 for Timeline at `2026-09-30T00:04:37+08:00`. The formal review is `runs/2026-09-27-001-bls-august-2026-employment-situation/human_visual_asset_review_candidate_3.json`, SHA-256 `a92d5d010c2ae2389ca8cd8c85da3bb5614dfaae684326e2e3390505004c11b3`. It binds Candidate 3 bundle SHA-256 `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355` to recovered Storyboard canonical SHA-256 `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded` and the current upstream review/dependency hashes. Candidate 1 and Candidate 2 reviews remain preserved.

The formal Timeline owner generated `timeline.json` schema `5.1`, SHA-256 `87730bfc54d84e5c1d2a10cdade67c9bea11dc4559a7915d5df6b19af8526d3a`. It preserves the nine approved scene IDs and exact ranges from `0` to `58,679 ms`, maps visuals 9/9, and composes all 12 canonical subtitle cues. The Timeline binds the approved narration SHA-256 `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183`, current alignment SHA-256 `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306`, subtitle track SHA-256 `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46`, Script SHA-256 `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305`, and the human audio/Storyboard/visual approvals. Motion uses restrained deterministic per-object fade-ins; it does not alter copy or factual semantics.

The local preview-only entry is `runs/2026-09-27-001-bls-august-2026-employment-situation/renderer_project/review-preview.html`, SHA-256 `0b77b76ded4713644e3d0dbd665a2c137e16516586535883db7e4a4d554bc31f`; it is marked `PREVIEW · NOT FINAL` and `HUMAN REVIEW REQUIRED`. Static QA confirms local audio/visual assets, 9/9 scene mapping, 12 subtitle cues, ordered in-bounds timing, contiguous scene ranges, and `full_render_requested=false`. The browser security policy blocked opening the local `file://` preview in this review pass, so visual appearance, browser playback, text clipping, and perceived sync have not been visually inspected by the agent. Alignment remains `proportional_by_normalized_char_count`, quality `estimated`, not word-level acoustic alignment. The review checklist is [PREVIEW_REVIEW.md](PREVIEW_REVIEW.md).

**Current gate: `HUMAN PREVIEW REVIEW = PENDING`.** No final-render approval, final MP4, publication, or V0.2 acceptance is recorded. Exact next action: human review of `PREVIEW_REVIEW.md` and the local `review-preview.html`.


## Current Phase 3C.5C — corrected preview awaiting human review

**`V0.2_PHASE_3C5C_WAITING_FOR_PREVIEW_REVIEW` · `HUMAN PREVIEW REVIEW = PENDING`**

Preview Candidate 1 has the explicit human `CHANGES_REQUIRED / SUBTITLE_OCCLUSION_AND_TIMING_SYNC` decision. Preview Candidate 2 is `TECHNICAL_RENDER_FAILURE / RENDER_TIME_AND_SUBTITLE_LAYOUT`, never registered for human review; it is not a human rejection. Both videos and old renderer packages are preserved.

Generic renderer fix `0e587cc` binds scenes, motion and captions to requested HyperFrames frame time, independently of audio playback. Full subtitle text is measured after browser font resolution; compact panels adapt to actual wrapping and safe free bands without clipping or covering measured critical objects/footers. No BLS/Fed-specific rendering branches or added font files are used.

The formal owner reused Timeline Candidate 2 unchanged (SHA-256 `3e60ff14724751cef59d252e013c76950db37cacc30f99f515aa4e1db9da6642`) and generated renderer/preview Candidate 3. All previously existing run files except owner-updated `run.json` remain byte-identical. Current MP4: `runs/2026-09-27-001-bls-august-2026-employment-situation/review-preview-candidate-3.mp4`; SHA-256 `0421363e620e56429e8b14b3dead33b5fbdbf99f1b0eda1ecece917b9738f4fe`. It is NON-FINAL, 3,889,121 bytes, 1080×1920, 30 FPS, H.264/AAC, 58.700 s video / 58.679 s audio.

Actual QA covered 9 scene interiors, 6 boundary frames, all 12 subtitle cues, and opening/ending. The 27 scene/boundary/cue frames match the compiled DOM; scene_003 is correct and scene_008's three lines are visible. Both DOM probes report zero clipping/footer/critical-object collision. Focused tests: 49 passed; safe non-integration: 958 passed (zero failures/skips); diff check passed. Font fallback and large-HTML lint messages remain documented non-blocking limitations. Timing remains pause-refined sentence timing, not word-level forced alignment.

**Exact next action: human review of Preview Candidate 3 and `cases/bls-aug-2026-employment/PREVIEW_REVIEW.md`.** No preview approval, final render, publication, push, merge, or V0.2 completion is authorized by this phase.
