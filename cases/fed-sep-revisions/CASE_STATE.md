# Fed SEP Revisions — Case State

- **Topic:** Federal Reserve SEP revisions (case label from `cases/fed-sep-revisions/`).
- **Fed Case 2 identity:** Resolved from the user's explicit case definition on 2026-09-24; this is a new Case 2 source set and does not identify or repair the legacy checkpoint.
- **Fed Case 2 status:** Identity is resolved. Native source run `2026-09-24-001-fed-sep-case-2-source-inventory` exists; its source package is approved and current, native facts 2.2 and Research synthesis exist. No new Fed V2 checkpoint has been built, approved, sealed, imported, or promoted.
- **Target SEP:** September 16, 2026 release; the FOMC meeting was September 15–16, 2026.
- **Comparison SEP:** June 17, 2026 release; the FOMC meeting was June 16–17, 2026.
- **Case question:** “从 2026 年 6 月到 9 月，美联储参与者对增长、失业率、通胀和利率路径的预测发生了什么变化？这些变化与 9 月会议公开表达的经济和通胀判断如何对应？”

## Fed Case 2 authoritative source set

The four required sources below are official Federal Reserve HTML pages. Their exact HTTPS URLs and release/meeting dates were checked on 2026-09-24, then ingested into the native source-inventory run listed above.

| Requirement | Official document | Release / meeting date | Exact URL | Content type | Case role |
|---|---|---|---|---|---|
| Required | September 16, 2026 FOMC Projections materials, accessible version (SEP) | Released September 16; meeting September 15–16, 2026 | <https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm> | HTML | Primary evidence for September participant projections. |
| Required | June 17, 2026 FOMC Projections materials, accessible version (SEP) | Released June 17; meeting June 16–17, 2026 | <https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm> | HTML | Primary evidence for the June comparison projections. |
| Required | September 16, 2026 FOMC statement | Released September 16, 2026 | <https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm> | HTML | Primary evidence for the Committee's public economic, employment, inflation, and policy assessment at the target meeting. |
| Required | June 17, 2026 FOMC statement | Released June 17, 2026 | <https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm> | HTML | Primary evidence for the Committee's public assessment at the comparison meeting. |

No optional supporting sources are selected at this checkpoint. Do not substitute media, blogs, FRED, or news coverage for these primary Federal Reserve materials. A press conference or transcript is out of scope unless the case question is later explicitly revised to require it.

## Overnight bounded run outcome (2026-09-25)

- **Source package:** The four locked Federal Reserve sources remain unchanged. Approved `authoritative_primary_set/1.0` package SHA-256: `32661017df86af572c91465bd0a1a5a21e9d0028554b8da7bdc061b702ee70eb`. `independent_source_count=1`; legacy `selection_status=insufficient_sources`.
- **Native facts:** `facts.json` schema `2.2`, 34 claims: 7 verified, 6 conflicted, 21 unverified. The five core 2026 SEP median comparisons are verified as `authoritative_primary_attestation`, with June/September values: real GDP `2.2 → 2.3`; unemployment `4.3 → 4.1`; PCE inflation `3.6 → 3.7`; core PCE inflation `3.3 → 3.4`; projected federal funds rate `3.8 → 4.1`. Values came from current source captures, not from case-document cues.
- **Research:** `research.md` exists and is registry-current (SHA-256 `07bc7c55e9c14c67c692aa081c89ad0fdcc455a406d0e1a6d9cafe49aa1e3fac`). Its inherited `questions.json` framing is about source inventory and includes causal questions; it needs formal owner-stage correction and Research regeneration before content planning.
- **Angle/script/video:** Angle generation failed closed with `AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED` using the existing GDP-specific local mock. No angle or script was produced. Video/TTS/renderer were not run.
- **Old checkpoint:** Its `ANGLE_FORMAL_FIELDS_MISSING` blocker and staging-only historical status are unchanged.
- **Full details:** See `docs/OVERNIGHT_REPORT_2026-09-24.md` and `docs/CURRENT_HANDOFF.md`.

## Projection comparison verification cues

The following values were supplied as expected comparison cues, not as approved facts or native-pipeline inputs. The future run must extract and verify every value from the official SEP artifacts before using it; do not copy these values into `facts.json`, a checkpoint draft, or other formal artifacts from this document.

| 2026 median projection | June cue | September cue |
|---|---:|---:|
| Real GDP growth | 2.2 | 2.3 |
| Unemployment rate | 4.3 | 4.1 |
| PCE inflation | 3.6 | 3.7 |
| Core PCE inflation | 3.3 | 3.4 |
| Projected appropriate federal funds rate | 3.8 | 4.1 |

The SEP is evidence of participants' projections. FOMC statements provide the Committee's public assessment. Do not turn correspondence into causation or infer motives the Fed did not state.

- **Implementation baseline:** Approved Checkpoint Authoring Workflow V1 and authoritative-primary runtime/materialization are implemented on the remote baseline. Overnight generic evidence and downstream-safety changes are on local branch `overnight/fed-sep-evidence-2026-09-24`; see the overnight report and current handoff for commits/Git state. These changes do not repair or unblock the original Fed checkpoint.
- **Fed Case 2 status:** The native source-inventory run and native facts 2.2 / Research artifacts exist. No new Fed `approved-checkpoint/2.0` or `2.1` checkpoint, import promotion, or production content run has been created.
- **Approved checkpoint status:** The staging canary input used `checkpoint_schema_version=approved-checkpoint/1.0`; the envelope gate reported no approval-status error. The original checkpoint body is absent from the staging package, so its approved angle values cannot be independently reconstructed from the canary artifacts.
- **Import status:** Staging only; not promoted. `.checkpoint-staging/cp-5ec4fb8d89137a2224d9/` contains `checkpoint_fingerprint.json` and `gates.json`. No materialized artifacts belong to the legacy checkpoint; the separate Case 2 native source run is under `runs/`.
- **Blocker:** `ANGLE_FORMAL_FIELDS_MISSING`. The missing formal `AngleCandidate` fields are `audience_relevance`, `controversy_risk`, `core_insight`, `core_question`, `eligibility`, `evidence_strength`, `explainability`, `hook`, `hook_strength`, `novelty`, `total_score`, and `visual_potential`. Provenance, fact-coverage, and script-coverage gates remain false because validation stopped before source capture and materialization.
- **Forensic recovery:** Completed read-only. The investigation covered current readable project files, all 40 locally reachable commits, local refs/branches/tags, reflog, dangling/unreachable Git objects, and readable ignored/untracked project files. No complete values with provenance tying them to this Fed approved checkpoint were found. The staging fingerprint identifies the failed canary input but does not contain its original body. Historical unreachable objects contain copies of the fingerprint/gates and handoff documentation, not the checkpoint body. GDP artifacts and test fixtures contain unrelated complete examples and are not valid Fed recovery sources.
- **Search limits:** GitHub live refs could not be queried because the local Git credential/channel request failed (`Schannel SEC_E_NO_CREDENTIALS`); this investigation does not claim that every remote GitHub ref was verified. `.pytest_cache/` was inaccessible due to local filesystem permissions, so it was outside the readable-file scan.
- **Recovery rule:** The original checkpoint remains blocked. Do not repair, backfill, infer, default, copy, or upgrade it to V2. GDP artifacts and test fixtures remain prohibited as recovery sources. The future Fed Case 2 path is a separate new, complete `approved-checkpoint/2.0` checkpoint, not revival of this old checkpoint.
- **Exact next step:** A human/operator must select or authorize a Fed-appropriate local/offline content-planning path and correct `questions.json` through its formal owner to match the locked Case 2 question. Then regenerate Research and retry angle generation. The existing GDP-specific mock fails closed; do not call a live provider without explicit authorization. The old Fed import remains blocked and is not part of Case 2.
