# BLS August 2026 Employment Situation — Case State

## Identity and current status

- Case ID: `bls-aug-2026-employment`
- Run ID: `2026-09-27-001-bls-august-2026-employment-situation`
- Status: **Phase 3A.1 evidence extraction and deterministic Research complete; current Facts and Research await human review.**
- Target: BLS Employment Situation — August 2026.
- Comparison source: BLS Employment Situation — July 2026 archive.
- No BLS angle, script, audio, storyboard, timeline, or video has been generated.

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

## Phase 3A.1 extraction contract and current Facts

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

## Current deterministic Research

`research_focus.json` and `research.md` are registry-valid/current. Research references exactly `claim_063` through `claim_071`; each is verified and allowed downstream. It preserves the household/establishment survey distinction, reports the June and July revision values from the August release, and shows several explicitly described industry increases and declines. It does not infer causes or combine survey measures. The remaining 62 records are excluded from substantive findings because they are unverified or not allowed downstream.

The reprocessing used only local artifacts. Search and fetch providers were replaced with fail-on-call stubs and were not called. Sources and normalized captures were not rewritten. No facts, source approvals, or case input values were manually inserted into the run artifacts.

## Verification and exact next action

Phase 3A.1 extraction-focused tests: 88 passed; expanded extraction/checkpoint/artifact regression: 188 passed. Safe non-integration regression: 723 passed. `git diff --check` passed before closeout.

**Exact next action: human review the current Facts 2.2 and deterministic Research artifacts, then stop.** Do not generate angles, select an angle, or enter Phase 3B as part of this handoff.
