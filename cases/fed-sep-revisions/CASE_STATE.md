# Fed SEP Revisions — Case State

- **Topic:** Federal Reserve SEP revisions (case label from `cases/fed-sep-revisions/`).
- **Fed Case 2 identity:** Resolved from the user's explicit case definition on 2026-09-24; this is a new Case 2 source set and does not identify or repair the legacy checkpoint.
- **Fed Case 2 status:** Identity is resolved. Native source run `2026-09-24-001-fed-sep-case-2-source-inventory` has the approved/current source package, Facts 2.2, current Research focus and Research, five eligible angles, human-selected `angle_001`, evidence-grounded script, human-approved Volcengine narration, sentence-level proportional timing, eight-scene visual plan, and final MVP MP4. The V0.1.0 video is published on the public `main` repository Release. No new Fed V2 checkpoint was created, imported, or promoted. See `docs/FED_CASE_2_DEMO.md` for the closeout record.
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

## Historical Fed Case 2 B2 framing and factcheck checkpoint (2026-09-25)

This section records the state at the earlier B2 handoff. Subsequent work completed content planning, human angle selection, script, narration, and the public V0.1.0 video MVP; those later results are summarized in the current status above and `docs/FED_CASE_2_DEMO.md`.

- **Source package:** The four locked Federal Reserve sources remain unchanged. Approved `authoritative_primary_set/1.0` package SHA-256: `32661017df86af572c91465bd0a1a5a21e9d0028554b8da7bdc061b702ee70eb`. `independent_source_count=1`; legacy `selection_status=insufficient_sources`.
- **Native facts:** `facts.json` schema `2.2`, 38 claims: 9 verified, 6 conflicted, and 23 unverified. The five core 2026 SEP median comparisons are `claim_022`, `claim_024`, `claim_025`, `claim_026`, and `claim_027`; each is verified as `authoritative_primary_attestation` and allowed downstream. September FOMC statement facts for economic activity (`claim_035`) and inflation (`claim_037`) are also verified and allowed downstream.
- **Research framing:** `research_focus.json` is current with SHA-256 `d6d1fa63fb8793657779dabdc0b7a572169c8681cb77f7a8c647b05498c31f0e`. It carries the locked Case 2 question, seven scoped subquestions, and constraints. `research.md` is registry-current with SHA-256 `3ee9a0eff9ee168d39d5c9c9bc319a877b5f492868bcb4df10d978d1a2cad89f`. The earlier source-inventory/causal framing in `questions.json` is no longer the content-planning frame; it remains a legacy acquisition artifact and is not an instruction to rerun B2.
- **Angle/script/video at B2 handoff:** At that earlier checkpoint, no angle, script, or video existed; the following Phase C1 work generated five eligible candidates and stopped for human selection. The current completed angle/script/video state is recorded in `docs/FED_CASE_2_DEMO.md`.
- **Old checkpoint:** Its `ANGLE_FORMAL_FIELDS_MISSING` blocker and staging-only historical status are unchanged. It remains unrelated to the new Case 2 native source run.
- **Next action at that historical B2 checkpoint:** Implement the generic offline angle planner and generate candidates, then stop for human selection. That action was completed in subsequent work: five eligible candidates were created, `angle_001` was selected, and the video MVP was rendered. The current completed state and exact limitations are recorded below and in `docs/FED_CASE_2_DEMO.md`.
## Historical projection comparison verification cues

At case-definition time, the following values were supplied as expected comparison cues, not as approved facts or native-pipeline inputs. The completed native run later extracted and verified its comparison facts from the official SEP artifacts. These historical cues are not evidence; do not copy them into `facts.json`, a checkpoint draft, or other formal artifacts.

| 2026 median projection | June cue | September cue |
|---|---:|---:|
| Real GDP growth | 2.2 | 2.3 |
| Unemployment rate | 4.3 | 4.1 |
| PCE inflation | 3.6 | 3.7 |
| Core PCE inflation | 3.3 | 3.4 |
| Projected appropriate federal funds rate | 3.8 | 4.1 |

The SEP is evidence of participants' projections. FOMC statements provide the Committee's public assessment. Do not turn correspondence into causation or infer motives the Fed did not state.

- **Implementation baseline:** Approved Checkpoint Authoring Workflow V1, authoritative-primary runtime/materialization, generic evidence extraction, downstream-safety, B2 Research focus, and factcheck changes are implemented on public `main`. These changes do not repair or unblock the original Fed checkpoint.
- **Fed Case 2 status:** The native source-inventory run, native facts 2.2, current Research focus, and current Research artifacts exist. Five eligible angles were generated, `angle_001` was selected by the user, and the selected-angle → script → human-approved narration → timeline → visual plan → MP4 chain is complete and publicly released as V0.1.0. No new Fed `approved-checkpoint/2.0` or `2.1` checkpoint was created, imported, or promoted; the native run and video MVP do exist.
- **Approved checkpoint status:** The staging canary input used `checkpoint_schema_version=approved-checkpoint/1.0`; the envelope gate reported no approval-status error. The original checkpoint body is absent from the staging package, so its approved angle values cannot be independently reconstructed from the canary artifacts.
- **Import status:** Staging only; not promoted. `.checkpoint-staging/cp-5ec4fb8d89137a2224d9/` contains `checkpoint_fingerprint.json` and `gates.json`. No materialized artifacts belong to the legacy checkpoint; the separate Case 2 native source run is under `runs/`.
- **Blocker:** `ANGLE_FORMAL_FIELDS_MISSING`. The missing formal `AngleCandidate` fields are `audience_relevance`, `controversy_risk`, `core_insight`, `core_question`, `eligibility`, `evidence_strength`, `explainability`, `hook`, `hook_strength`, `novelty`, `total_score`, and `visual_potential`. Provenance, fact-coverage, and script-coverage gates remain false because validation stopped before source capture and materialization.
- **Forensic recovery:** Completed read-only. The investigation covered current readable project files, all 40 locally reachable commits, local refs/branches/tags, reflog, dangling/unreachable Git objects, and readable ignored/untracked project files. No complete values with provenance tying them to this Fed approved checkpoint were found. The staging fingerprint identifies the failed canary input but does not contain its original body. Historical unreachable objects contain copies of the fingerprint/gates and handoff documentation, not the checkpoint body. GDP artifacts and test fixtures contain unrelated complete examples and are not valid Fed recovery sources.
- **Search limits:** GitHub live refs could not be queried because the local Git credential/channel request failed (`Schannel SEC_E_NO_CREDENTIALS`); this investigation does not claim that every remote GitHub ref was verified. `.pytest_cache/` was inaccessible due to local filesystem permissions, so it was outside the readable-file scan.
- **Recovery rule:** The original checkpoint remains blocked. Do not repair, backfill, infer, default, copy, or upgrade it to V2. GDP artifacts and test fixtures remain prohibited as recovery sources. Any future checkpoint need for Case 2 must use a separate complete approved checkpoint built from the native formal artifacts, never revival of this old checkpoint.
- **Video MVP:** Final file `runs/2026-09-24-001-fed-sep-case-2-source-inventory/final.mp4`; 1080×1920, 30 FPS, H.264/AAC, approximately 74.633 seconds. It contains eight scenes and twelve sentence-level caption segments. Caption timing uses proportional sentence timing, not WhisperX word-level forced alignment. Full details, source and publication provenance, facts/research/angle/script state, tests, and remaining limitations are in `docs/FED_CASE_2_DEMO.md`.
- **Current closeout boundary:** V0.1.0 implementation and video are already public on `main`. This documentation-only closeout commit is local and awaits separate push authorization. Read actual Git state for current HEAD and worktree; stop after closeout and do not continue into another pipeline phase without new direction.
