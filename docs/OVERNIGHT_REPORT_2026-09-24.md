# Overnight Report

- **Start commit:** `4ec89bc6b59a128d24a75ca4fdcc776e3fe25f91`
- **Engineering end commit before documentation closeout:** `1af73e4ac9d837743deb1dcd06425dc70ed9a086`
- **Branch:** `overnight/fed-sep-evidence-2026-09-24`
- **Start time:** `2026-09-24T23:33:12.5782302+08:00`
- **Report closeout time:** `2026-09-25T00:57:11+08:00` (before the final documentation-only commit)

## Executive summary

本夜完成了通用表格证据结构化提取与内容下游的权威归属保护，并离线重跑了 Fed Case 2 factcheck 和 Research。五项核心 SEP 比较均已核验通过。现有 GDP 专用 mock 无法产生三个符合 Fed 归属边界的角度，angle 阶段因此 fail closed。未产生 script/video，也未调用 live provider、网络或 TTS。

## Milestones completed

1. Implemented generic, fail-closed structured table evidence extraction. The evidence binds a metric row to its header context, statistic, period, value, unit, source document, and stable line locator. Ambiguous table structure fails closed; paragraph evidence behavior remains covered.
2. Reran Fed B1 offline through `stop_after="factcheck"`. The five core SEP comparisons are each verified with `verification_basis=authoritative_primary_attestation`, `authority_attestation.kind=deterministic_document_comparison`, and `allowed_downstream=true`.
3. Ran the existing deterministic Research synthesis offline. `research.md` is registered current, but its inherited source-inventory questions/title and causal-question framing are not aligned with the locked Case 2 question and require correction through the formal questions owner before reuse for final content planning.
4. Audited and hardened authority safety in angle/script paths: attribution and scope metadata are retained, and generic fail-closed checks reject unsupported scope expansion, dropped attribution, projection-to-commitment changes, and causal/motive claims.
5. Attempted the existing local mock angle path. It failed closed with `AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED`; no angle was written. Per bounded scope, Script and Video were stopped.

## Files changed

Engineering commits changed these 13 files:

- `src/fanglei/research.py`
- `src/fanglei/authority_safety.py`
- `src/fanglei/angle_policy.py`
- `src/fanglei/content_models.py`
- `src/fanglei/content_policy.py`
- `src/fanglei/providers/content.py`
- `src/fanglei/script_lint.py`
- `tests/test_structured_table_evidence.py`
- `tests/test_authoritative_primary_runtime.py`
- `tests/test_angle_policy.py`
- `tests/test_deepseek_content.py`
- `tests/test_script_quality.py`
- `tests/test_v03_core.py`

Documentation closeout files: `docs/OVERNIGHT_REPORT_2026-09-24.md`, `docs/CURRENT_HANDOFF.md`, `docs/PROJECT_STATE.md`, and `cases/fed-sep-revisions/CASE_STATE.md`.

No Fed `facts.json`, `research.md`, source artifacts, approvals, or registry files were committed or manually edited during the engineering changes; pipeline artifacts remain in the run directory.

## Local commits created

- `4c5afbaecb3e2d2040fb321130ead54bb0bfdd5d` — `fix: extract structured table evidence safely`
- `36aa46b5342d63a6be7d7a6fe1f09dce0e2d13a7` — `fix: retain structured table header locators`
- `1af73e4ac9d837743deb1dcd06425dc70ed9a086` — `fix: preserve authority scope through content pipeline`

A separate documentation-only closeout commit follows this report. Nothing was pushed.

## Tests

- Structured-table / authority / research focused command:

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_structured_table_evidence.py tests/test_authoritative_primary_runtime.py tests/test_v02_research.py -q -p no:cacheprovider --basetemp .venv/pytest-tmp-phase1-final
  ```

  Result: **36 passed**.

- Downstream authority focused regression covered `tests/test_angle_policy.py`, `tests/test_script_quality.py`, `tests/test_deepseek_content.py`, and `tests/test_v03_core.py`: **50 passed**. The exact shell invocation was not preserved in the run notes.

- Safe full non-integration suite (final successful run):

  ```powershell
  .venv\Scripts\python.exe -m pytest tests --ignore=tests/integration -p no:cacheprovider --basetemp .venv/t -q
  ```

  Result: **629 passed** in 218.50 seconds.

- An earlier full-suite attempt using a deeply nested temporary directory had **29 path-related failures and 180 passes**; the failures were Windows temporary-path `FileNotFoundError` cascades. The suite was rerun with the repository's short basetemp `.venv/t` and passed all 629 tests. No ordinary failures were skipped.
- `git diff --check`: passed after engineering changes; rerun for documentation closeout.
- No staging, live provider, network, or TTS was used for this overnight work.

## Fed pipeline state

Run: `runs/2026-09-24-001-fed-sep-case-2-source-inventory/`.

- **Sources:** Four approved Federal Reserve sources remain unchanged. `sources.json` SHA-256: `66687d3c887e45b094ca6a2e0e7487d22906f257832411ef840ba322c9d1ce57`. Source index SHA-256: `e2c2d2dda1f473c0d933421a2ed015a041b9ac171d6174d0c87f7871ece77b65`. Approved package SHA-256: `32661017df86af572c91465bd0a1a5a21e9d0028554b8da7bdc061b702ee70eb`. Package is admissible; independent source count is still `1`; legacy `selection_status` is still `insufficient_sources`.
- **Facts:** `facts.json` schema `2.2`; 34 claims: 7 verified, 6 conflicted, 21 unverified. Artifact SHA-256: `96cfa17237412a1733ac5051c88546e77732fdaca94fd13ad30833fc8ee194b0`.
- **Core five comparisons:**

  | Claim | Metric | June 2026 | September 2026 | Change | Verification |
  |---|---|---:|---:|---:|---|
  | `claim_022` | Real GDP growth median | 2.2% | 2.3% | +0.1 pp | verified / authoritative primary attestation |
  | `claim_024` | Unemployment rate median | 4.3% | 4.1% | -0.2 pp | verified / authoritative primary attestation |
  | `claim_025` | PCE inflation median | 3.6% | 3.7% | +0.1 pp | verified / authoritative primary attestation |
  | `claim_026` | Core PCE inflation median | 3.3% | 3.4% | +0.1 pp | verified / authoritative primary attestation |
  | `claim_027` | Federal funds rate median | 3.8% | 4.1% | +0.3 pp | verified / authoritative primary attestation |

  These values were extracted from the current June and September local SEP captures, not copied from case-document cues. Each comparison cites `src_002` and `src_001` respectively.
- **Statement facts:** `claim_033` is an attributed September-statement report of the statement's sentence, “Today's policy action will support a timelier return to the Committee's 2 percent goal.” `claim_034` is an attributed June-statement report that inflation remained elevated relative to the Committee's 2 percent goal, partly reflecting supply shocks and energy-sector price increases. Both are authority attestations; neither is used to infer why the SEP median changed.
- **Research:** `research.md` SHA-256 `07bc7c55e9c14c67c692aa081c89ad0fdcc455a406d0e1a6d9cafe49aa1e3fac` (8,303 bytes), registry state current. Content framing inherits source-inventory questions, including causal-mechanism questions; correct `questions.json` through its formal owner and regenerate Research before angle work.
- **Angle:** failed; error `AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED`. No `angles.json` or selected angle.
- **Script:** not run; `script.json` and `script.md` are missing.
- **Video:** not inspected or run because there is no valid script. No storyboard, narration, TTS, alignment, renderer, or MP4 was produced.

## Key outputs

- Structured table extractor: `src/fanglei/research.py`; focused fixtures: `tests/test_structured_table_evidence.py`.
- Authority propagation and safety checks: `src/fanglei/authority_safety.py`, `src/fanglei/angle_policy.py`, `src/fanglei/script_lint.py`, and related tests.
- Fed run facts: `runs/2026-09-24-001-fed-sep-case-2-source-inventory/facts.json` — SHA-256 `96cfa17237412a1733ac5051c88546e77732fdaca94fd13ad30833fc8ee194b0`.
- Fed run Research: `runs/2026-09-24-001-fed-sep-case-2-source-inventory/research.md` — SHA-256 `07bc7c55e9c14c67c692aa081c89ad0fdcc455a406d0e1a6d9cafe49aa1e3fac`.

## Blockers

- **Angle blocker:** the only existing local planning mock used here is GDP-specific; its output did not yield three distinct candidates that passed the Fed authority/scope checks. The formal gate correctly rejected the attempt with `AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED`.
- **Research framing blocker:** `questions.json` still reflects source-inventory framing, including causal questions, rather than the locked Fed Case 2 question. Although Research is registry-current, it is not ready to serve as final content framing until its input is corrected by the formal owner and Research is regenerated.
- No valid angle or script exists; therefore video readiness is unassessed.

## Human decisions required

- Select or authorize a Fed-appropriate local/offline content-planning path; do not infer that a live provider is approved.
- Confirm the formal question-owner correction to `questions.json` against the locked Case 2 question before rerunning dependent Research.
- No human approval or checkpoint approval was fabricated or written overnight.

## Risks / things to review

- The full suite initially hit Windows temp-path failures under an overly deep basetemp; the short-basetemp rerun was fully green (629 passed).
- Research's current artifact hash is valid, but registry freshness does not resolve its stale/inappropriate question framing.
- Twenty-one facts remain unverified and six are conflicted; downstream content must continue to honor `allowed_downstream` and verification basis.
- The original legacy Fed checkpoint remains blocked by `ANGLE_FORMAL_FIELDS_MISSING`; this run did not repair, backfill, infer, default, copy, or upgrade it.
- The overnight branch is local only and has not been pushed.

## Recommended next action

Have the human/operator select or authorize a Fed-appropriate offline content-planning path and approve correction of the formal `questions.json` input to the locked Case 2 question. Then use the existing owner-stage APIs to regenerate Research and retry angle generation; stop again if fewer than three eligible angles are produced. Do not call a live provider or proceed to script/video/TTS without authorization and valid upstream artifacts.

## Git state

- **Branch:** `overnight/fed-sep-evidence-2026-09-24`
- **Engineering HEAD before report-only closeout:** `1af73e4ac9d837743deb1dcd06425dc70ed9a086`
- **origin/main:** `4ec89bc6b59a128d24a75ca4fdcc776e3fe25f91`
- **Ahead/behind before report-only closeout:** `3/0`
- **Working tree before documentation closeout:** clean
- **Push:** none
