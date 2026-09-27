# BLS August 2026 Employment Situation — Case State

## Identity

- Case ID: `bls-aug-2026-employment`
- Run ID: `2026-09-27-001-bls-august-2026-employment-situation`
- Status: **`PHASE_3A_BLOCKED_GENERALIZATION_GAP`**. Formal source approval, partial Facts 2.2, Research Focus, and Research exist. The shared extractor cannot produce complete eligible evidence for the locked question without a generic capability decision.
- Target: BLS Employment Situation — August 2026.
- Comparison: BLS Employment Situation — July 2026 archive.

## Locked research question

2026 年 8 月美国就业报告中，非农就业、失业率、工资和工时发生了什么变化？6 月与 7 月非农就业数据被如何修正，哪些行业对 8 月就业变化贡献较大或形成拖累？

The case asks what the BLS documents report. It does not ask for causes, Federal Reserve policy effects, recession or soft-landing conclusions, market effects, political implications, or future rate implications.

## Approved source package and capture state

| Source | Exact URL | Reviewed publication date | Normalized text SHA-256 | Raw capture hash |
|---|---|---:|---|---|
| `src_001` — Employment Situation, August 2026 | <https://www.bls.gov/news.release/empsit.htm> | `2026-09-04` | `4a4491e19010fb560aefdccd072463ad400b51d628a1a7df60ba3d75ff2db121` | `null` |
| `src_002` — Employment Situation, July 2026 archive | <https://www.bls.gov/news.release/archives/empsit_08072026.htm> | `2026-08-07` | `8e43fdb02dae6381dbf793f3e37789a69aa0cef9864ede493175e3b416ab4e07` | `null` |

Both publication dates were approved by `motty63-ctrl` at `2026-09-27T20:04:42+08:00`, bound to the exact normalized-text hashes and line 38 release-header excerpts. The reviews were applied through `apply_publication_date_reviews()`; normalized capture bytes, source IDs, and URLs remained unchanged.

The `authoritative_primary_set/1.0` package was approved by `motty63-ctrl` at the same timestamp. Its package SHA-256 is `13680d96d487497ed19d95ecbd09ccbf213e732f6787dc066320e11ed44355d9`. The approval is limited to these two BLS source documents and their evidence roles; it does not approve future claims or causal, motive, or market-impact interpretations.

`source_documents/index.json` and `sources.json` are registry-valid/current. `sources.json` is schema `2.1`, package admissibility is `admissible`, independent source count remains `1`, legacy `selection_status` remains `insufficient_sources`, and `fetch_errors` is empty. No additional source was added.

## Facts and Research result

Facts were produced through `run_v02_pipeline(..., stop_after="factcheck", authority_claims=...)` from the local captures. `facts.json` is native schema `2.2`: **62 claims total — 7 verified, 1 conflicted, 54 unverified**. All seven verified claims use `authoritative_primary_attestation`, are `fact` claims, and have `allowed_downstream=true`; no cross-document deterministic comparison was verified.

The seven eligible document-report claims cover the August payroll change, August unemployment rate, two August industry movements, the June revision direction/amount as recorded in the captured excerpt, and two values from the prior July release. They are direct BLS-attributed report excerpts. Several normalized lines end mid-sentence; Research preserves those exact excerpts and does not complete them from adjacent, unbound text.

`research_focus.json` and deterministic `research.md` are registry-valid/current. Research contains only the seven eligible claims and explicitly separates household-survey unemployment from establishment-survey payroll employment, hours, and earnings. It does **not** fully answer the locked question: no eligible fact covers average hourly earnings, average workweek, or the complete July revision; the June old/revised values are also not established as eligible claims. These remain omitted/unverified.

## Generalization gap

The existing generic evidence path is insufficient for this BLS capture format:

- `RuleBasedEvidenceExtractor` does not include earnings/hours terms in its marker set, so the report’s wage and workweek evidence is not emitted for fact verification.
- `_structured_table_evidence()` returns zero rows for each captured BLS document; its existing table-shape assumptions do not recognize these normalized BLS tables.
- The August release’s revision passage is split across normalized lines. The current extractor emits only the line containing a recognized employment marker, not the continuation carrying the remaining revision values. A July revision comparison therefore cannot be verified through the current shared evidence groups.

No BLS-specific parser, production code, schema, tests, or run input was changed to bypass this limitation. Unverified records remain excluded from Research.

## Next action and phase boundary

**Stop Phase 3A and obtain a human decision on a generic, non-BLS-specific evidence extraction/locator contract before resuming.** Do not add a BLS branch or manually join lines/construct facts under this phase. After any separately approved generic fix, re-run the affected owner path and have a human review sources, facts, and Research. No Angle, Script, TTS, storyboard, timeline, or video was generated for this case.

## Verification

Safe non-integration regression: `.venv\Scripts\python.exe -m pytest tests --ignore=tests/integration -p no:cacheprovider --basetemp .venv/pytest-tmp -q` — **707 passed**. No production code or tests were changed in this Phase 3A attempt.
