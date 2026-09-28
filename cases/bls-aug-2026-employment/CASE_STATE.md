# BLS August 2026 Employment Situation — Case State

## Identity and current status

- Case ID: `bls-aug-2026-employment`
- Run ID: `2026-09-27-001-bls-august-2026-employment-situation`
- Status: **Phase 3A human review approved for Angle Planning only; five eligible Phase 3B.2 candidates generated; `angle_001` explicitly selected; Phase 3C.1.3 terminology decisions recorded (40 approved, 6 numeric entries rejected as non-terminology, 0 pending); the formal map is current; Script generation has not yet been retried.**
- Target: BLS Employment Situation — August 2026.
- Comparison source: BLS Employment Situation — July 2026 archive.
- Five BLS angle candidates have been generated and `angle_001` was human-selected. The formal terminology map is current. No valid Script, audio, storyboard, timeline, or video has been generated for this run.

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

## Current Phase 3C.1.3 — terminology approved; Script review pending

The selected angle is `angle_001`. Facts, Research Focus, Research, `angles.json`, and `angle_selection.json` remain current and unchanged. Their recorded SHA-256 values are Facts `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`, Focus `fe638d26622e271951365188f9fe0ba0b474ee2fb3bde3c544e0e91f4098b32a`, Research `ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862`, Angles `32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8`, and selection `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77`.

Phase 3C.1 and 3C.1.1 are retained as historical blocked checkpoints: English authoritative claims could not safely validate Chinese narration through literal proposition matching. Phase 3C.1.2 adds a generic, Facts-hash-bound `script-terminology-map/1.0` contract, cross-language validation foundations, structured numeric/revision/scope checks, bounded attribution context, duration-target quality, repair editability, and generic closing checks. Phase 3C.1.3 records the human decisions through the formal owner; it does not change Facts, Research, the selected angle, or terminology trust rules.

The 46-entry review in [TERMINOLOGY_REVIEW.md](TERMINOLOGY_REVIEW.md) records **40 APPROVED / 6 REJECTED_AS_NON_TERMINOLOGY / 0 PENDING**. Reviewer `motty63-ctrl` recorded the decisions at `2026-09-28T14:57:47+08:00`. The formal map at `runs/2026-09-27-001-bls-august-2026-employment-situation/script_terminology.json` is bound to case `bls-aug-2026-employment`, this run, and Facts SHA-256 `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`; its artifact SHA-256 is `a9ee561650535b58d3c6f5bb36c30a884225f70c202f6f0923e2954f05262d2c`. The corrected `term_a8efeac80fd5` decision maps `change` (metric; `claim_067`, `claim_068`) to `变动`, with approved alias `变化`. The six numeric entries are excluded from the trusted terminology map and remain represented by structured Facts fields.

After recording the human map, terminology/selection/script-quality focused validation passed **103 tests** and the safe non-integration regression passed **796 tests**. The checks used offline/local fixtures; no live Script call has yet been made in this phase.

Exact next action: revalidate the current Facts, Research, selected-angle record, terminology map, and Script entry dependencies; then use the formal V0.2 Script owner for one initial DeepSeek generation and at most two bounded repairs. If a valid Script is produced, prepare `SCRIPT_REVIEW.md` and stop for separate human Script review. Do not regenerate Facts, Research, or angles; do not start TTS or video production.
