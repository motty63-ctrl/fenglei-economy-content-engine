# V0.2 Workflow Generalization Plan

## Purpose and scope

V0.2 will turn the proven Fed Case 2 video MVP into a reusable economic short-video workflow. This is a bounded generalization effort, not a rewrite. V0.1.0 remains frozen and publicly available; its release, tag, and verified Fed video are not changed by this plan.

Phase 0 is documentation-only. The development branch `v0.2/generalize-video-workflow` starts from `origin/main` at `148d2ebdaee1437c038ead4631a5953d42b9a392`. The verified V0.1.0 safe non-integration baseline is 672 passing tests. No production code, tests, or Fed run artifacts were changed for this inventory.

## 1. V0.1.0 baseline

The completed Fed Case 2 path used an approved four-document Federal Reserve source package, reviewed publication metadata, native Facts 2.2, five verified SEP comparisons, a locked Research Focus, deterministic Research, five eligible offline angle candidates, a user-selected angle, an evidence-grounded script, human-approved Volcengine narration, an eight-scene plan, proportional sentence timing, and a validated 1080×1920 MP4. The public `v0.1.0` Release contains the final video.

The V0.1 deliverable is real and complete for that case. The findings below describe generalization gaps in shared production paths; they do not invalidate the released video or its case-specific outputs. The old Fed approved checkpoint remains historically blocked by `ANGLE_FORMAL_FIELDS_MISSING`; V0.2 does not repair or upgrade it.

## Phase 1A result — Search and Research Focus

Phase 1A is complete on `v0.2/generalize-video-workflow`. The shared search builder now composes requests only from supplied topic, claim, question/purpose, source-type, entity, measure, period, and subquestion inputs. Fetch context consumes explicit country/year/indicator metadata, with generic year extraction as fallback; it no longer guesses a country or GDP indicator from prose. The Research Focus renderer presents the supplied question, subquestions, constraints, and dynamically grouped source roles without fixed Fed/SEP sections; role grouping uses approved-document order and a stable source-order/ID fallback.

The existing `research-focus/1.0` schema and stored Fed run artifacts were not changed. A read-only render check confirmed the current Fed focus question and constraints, all four approved document roles, and the nine current `verified + allowed_downstream` fact records remain represented. New synthetic retail-sales tests cover generic search and focus rendering, including stable grouping when claim source IDs arrive in different orders. Focused tests: 55 passed. Safe non-integration regression: 676 passed. Phase 1A did not change Script providers, angle selection, eligibility predicates, storyboard/visual generation, TTS, alignment, or rendering.

## 2. Generalization gaps

| Area and owner | Current behavior | Why it is not general | V0.1 Fed impact | Recommended direction | Risk |
|---|---|---|---|---|---|
| Search request construction — `src/fanglei/pipeline.py::_search_requests` | **Resolved in Phase 1A.** Builds requests from explicit topic/context, verification claims, research question/purpose/source types, and optional entities/measures/periods/subquestions. It adds no default domain or topic phrase. | The previous shared default injected GDP wording and named-authority expansions. This specific gap is closed; future schema work may make structured input fields first-class, but generic code remains data-driven. | Fed terms and period remain present when supplied by the case inputs; no Fed run artifact was rewritten. | Keep the builder generic. Add new input fields only through a separately reviewed contract change; pass domain restrictions explicitly when the input contract supports them. | Search recall depends on the quality of authored questions and claims; there is no implicit topic-specific fallback now. |
| Fetch context — `src/fanglei/pipeline.py::_fetch_context` | **Resolved in Phase 1A.** Consumes explicit `country`, `years`, and `indicators`; years can be extracted generically from question text when explicit years are absent. | The previous helper guessed USA and `real_gdp_growth` from matching text. It now leaves unspecified country/indicator fields empty. | Existing Fed V0.1 captured artifacts were untouched. New runs must supply explicit context if a fetcher needs it. | Keep context optional and explicit; do not restore prose-to-country/indicator guesses in the shared path. | Legacy runs that relied on implicit fetch enrichment may need an explicit input adapter, not a hidden default. |
| Focused Research rendering — `src/fanglei/pipeline.py::_render_research_focus` | **Resolved in Phase 1A.** Displays the Focus question, subquestions, constraints, and eligible claim records grouped by supplied approved-document evidence roles (falling back to source metadata). It keeps the `verified` plus `allowed_downstream` predicate. | The previous renderer classified only hardcoded `sep` and target `statement` categories and emitted fixed date/institution headings. The renderer now structures input metadata rather than naming a case. | Fed participant/Committee attribution and the no-causality framing remain in the claim text, source roles, and Focus constraints. The stored `research.md` was not rebuilt. | Keep case meaning in reviewed Focus/source-role inputs. Add a structured role-to-question selection contract only as a separately versioned follow-up if varied cases show that display grouping alone does not scope Research sufficiently. | Generic display grouping cannot prove semantic relevance to a subquestion; review outputs for over-broad allowed facts and avoid claiming the renderer performs entailment. |
| Legacy Research rendering — `src/fanglei/pipeline.py::_render_research` | Includes every claim whose `verification_status` is `verified`; it does not also require `allowed_downstream == true`. | The legacy path and Research Focus path have different fact-eligibility rules. The focused path requires both verified status and downstream permission. | Fed Case 2 used the focused path, which filtered on both fields; its released Research is unaffected. | Centralize the eligibility predicate for new runs, with a named compatibility adapter for legacy artifacts if behavior must remain unchanged. Version any intentional contract change. | Tightening the legacy path could alter historical Research output; changing it silently would violate compatibility. |
| Live DeepSeek script generation — `src/fanglei/providers/content.py::DeepSeekContentPlanningProvider.generate_script` | The system and user prompts prescribe a 2024 U.S. GDP comparison, BEA/World Bank values, a fixed rounding explanation, fixed GDP hook, and a fixed GDP narrative beat list. | The live provider is not generating a script from the supplied selected angle and fact palette in a topic-neutral way; it carries a GDP calibration prompt into unrelated topics. | Fed V0.1 did not use this live script provider; it used the offline/mock content path. This is not a defect in the released Fed script. | Replace the fixed narrative with a prompt assembled from the selected angle, eligible claims, Research Focus, authority constraints, and output contract. Keep the provider constrained to those inputs and validate with existing local lint. | Prompt changes may affect output quality and repair rates. Use recorded fixtures and no-network tests; keep live-provider evaluation separate. |
| Offline/mock script planning — `src/fanglei/providers/content.py::MockContentPlanningProvider` | The authority path recognizes Fed comparison measures as named Chinese labels; the fallback path also has educational GDP-oriented narrative assumptions. | Mock behavior used for deterministic production-like runs is partially tuned to one topic, so another case may get incomplete labels or unsuitable narrative beats. | The Fed V0.1 case used this local path; its five metrics and resulting script were supported. | Make deterministic wording derive from claim metadata (metric, period, unit, comparison direction, attribution) and selected-angle structure; avoid an exhaustive topic switch. | Metadata may not carry enough display information. Fail visibly or use a neutral label; do not invent semantic descriptions. |
| Angle selection — `src/fanglei/content_pipeline.py::run_content_pipeline` and CLI `select-angle` / `plan-content` | Angle generation stores `recommended_angle_id` and marks `system_recommendation_human_selection_pending`. `stop_after="angle_generation"` leaves candidates for review. Continuing the API pipeline selects `angle_id` or silently falls back to the recommendation; CLI `select-angle` and `plan-content` can therefore choose the recommended candidate when no ID is provided. | The artifact says human selection is pending, but a normal continuation can turn the recommendation into a selection without a human action. The human gate is optional in runtime, not enforced by the shared contract. | The user explicitly selected `angle_001` for Fed Case 2; the delivered case did have human selection. Other callers can behave differently. | Separate `recommended_angle_id` from a recorded explicit selection event. For the V0.2 production path, require a supplied selected ID or a human-selection record before script generation; keep any legacy auto-select route clearly named and tested. | Enforcing a new gate can interrupt existing CLI workflows. Introduce it in the new workflow contract and preserve an explicit legacy mode until migration is approved. |
| GDP storyboard branch — `src/fanglei/storyboard.py::build_storyboard` | Detects exact `2.8%` and `2.7932%` text with BEA/World Bank references and creates named GDP fact objects, fixed year/indicator labels, and rounding visuals; otherwise it uses a generic builder. | Topic semantics and IDs are encoded in shared storyboard production code instead of supplied by a reusable visual plan. | The released Fed case did not match this GDP branch and used the generic storyboard path. | Move specialized GDP rendering to an explicitly named legacy/calibration adapter. General storyboard construction should consume typed scene objects and claim metadata only. | Removing or changing the branch could affect GDP calibration outputs. Preserve it behind its current compatibility boundary and add a generic-path regression test. |
| GDP visual semantics — `src/fanglei/providers/visual.py` | `_visual_semantics` activates fixed GDP story beats when the same numeric/source tokens appear; generic beats are used otherwise. | The visual provider can emit a content-specific storyboard from incidental text matching, which is brittle and not auditable as an explicit plan. | Fed V0.1 used generic visual semantics. The GDP calibration case remains a separate compatibility fixture. | Pass explicit typed visual concepts/layout requests from the storyboard; remove production dependence on numeric/string pattern matching. | Text matching can be part of legacy calibration behavior. Do not delete it until its fixtures and ownership are isolated. |
| GDP text calibration — `src/fanglei/storyboard_quality.py`, `src/fanglei/subtitle_generation.py`, `src/fanglei/alignment_matching.py` | Quality checks contain BEA/World Bank/GDP precision phrases; subtitle emphasis contains GDP-rounding terms; alignment normalization includes the exact GDP spoken forms. | Multiple downstream modules carry one demo's text and numeric forms, increasing the surface area of accidental topic coupling. | Fed V0.1's metrics did not rely on these exact calibration values; its sentence-level timing and render completed. | Move only exact calibration behavior into named legacy fixtures/adapters. Keep generic number detection, caption layout, and alignment logic independent of topic text. | Aggressive cleanup could break V0.1/GDP regression fixtures; preserve tested legacy behavior and use explicit compatibility tests. |
| Renderer entry-point clarity — `docs/RUNBOOK.md`, `src/fanglei/cli.py` and renderer APIs | The Fed MP4 exists and is released, while the documented CLI exposes renderer preparation/preflight rather than a complete final-render command; some video assembly is driven through APIs/tooling. | The end-to-end result is demonstrable, but a new developer cannot infer a single supported, reproducible render entry point from the CLI documentation alone. | It does not invalidate the released artifact; it limits repeatability for the next case. | Document the actual supported API/steps and artifacts before adding a new command. Consider a generic render owner only after its inputs, side effects, and approvals are explicit. | A thin wrapper could conceal provider, filesystem, or approval side effects; do not claim one-command reproduction until verified. |

### Other existing boundaries to preserve

- `src/fanglei/offline_angle_planner.py` is topic-neutral at its input boundary (Research Focus and claims), but its templates, diversity tests, and heuristic scores are fixed. Treat scores as deterministic product heuristics, not objective quality measurements; calibrate them against varied cases before presenting them as universally meaningful.
- `src/fanglei/angle_policy.py` and `src/fanglei/content_policy.py` provide policy/risk and script-ready claim filtering. Their behavior should be covered by the shared eligibility contract rather than replicated in each renderer.
- `src/fanglei/visual_project_v1.py` and `src/fanglei/gdp_calibration_v1.py` are explicitly named GDP calibration/legacy components. Preserve their compatibility; do not mistake their existence for the generic Fed video path.
- The actual Fed Case 2 video path used sentence-level proportional caption timing, not WhisperX word-level forced alignment. This remains an explicit V0.1 limitation.

## 3. V0.2 target contract

| Layer | Contract |
|---|---|
| Evidence | Capture exact source identity, source/document role, content hashes, and provenance. Source policy approval controls package admissibility only; it does not verify claims. |
| Facts | Store claims, evidence links/locators, verification status and basis, attribution, scope, and `allowed_downstream`. Do not infer a missing semantic value. |
| Research Focus | Store explicit run-bound primary question, subquestions, and framing constraints. It is case input, not a production-code topic template. |
| Research | Deterministically synthesize from claims meeting one centralized eligibility rule; cite claim/evidence/source identities. Render sections from focus structure rather than institution-specific sections. |
| Angle | Produce distinct proposals with support limited to eligible claims. Keep system recommendation separate from explicit human selection. |
| Script | Generate from the selected angle and eligible claim palette. Preserve attribution/scope; lint factual bindings and reject unsupported expansion. A lint pass is not proof of natural-language entailment. |
| Audio | Narrate the approved script; record provider/output identity and bind human voice approval to the audio hash before downstream production use. |
| Storyboard | Map script beats and verified data to typed visual objects and generic templates. No Fed/GDP conditionals in the ordinary shared path. |
| Timeline | Bind scene/sentence timing to audio and alignment artifacts. Clearly label proportional estimates versus measured alignment. |
| Renderer | Build and validate a reproducible video artifact from approved upstream artifacts. Document the actual entry point and side effects; do not imply an unsupported one-command CLI. |

## 4. Human gates

### Must be explicitly human-confirmed

- Approval of an authoritative source package when that source mode is used.
- Selection of the angle that proceeds to the V0.2 production script; a system recommendation alone is not a selection.
- Voice/narration approval bound to the exact audio hash before production rendering.
- Final media QA and any public release decision.

### May run automatically

- Artifact hashing, identity/dependency freshness validation, schema validation, evidence eligibility checks, and deterministic claim/source mappings.
- Research synthesis and offline angle proposal/ranking, provided outputs remain auditable and do not bypass policy gates.
- Script lint, storyboard/timeline construction, render preflight, and deterministic artifact checks after their required human gates are satisfied.

### Automatic recommendation with human override

The system may recommend an angle and may recommend visual treatments. It must preserve the recommendation as a suggestion, provide an explicit override path, and not represent a default recommendation as human approval. Policy thresholds can identify risk; they cannot approve facts or content on a person's behalf.

## 5. Migration plan

Each phase has a narrow artifact boundary, focused tests, a safe non-integration regression run before integration, and a rollback by reverting that phase's commit. Do not combine phase commits merely to reduce commit count.

| Phase | Scope and exit check | Rollback boundary |
|---|---|---|
| Phase 1A — Search and Research Focus | **Complete.** Use supplied input fields for search/fetch context; structure Research Focus from authored questions, constraints, and source roles. Synthetic non-Fed fixtures and Fed input compatibility pass; 55 focused and 676 safe non-integration tests pass. | Revert only the Search/Focus helper and its tests/docs; no run artifacts or V0.1 release changed. |
| Phase 1B — Content provider generalization | Replace fixed GDP narrative beats in live DeepSeek and mock script generation with selected-angle, eligible-claim, Research Focus, and authority-scope inputs. Add deterministic synthetic non-GDP script fixtures and retain local lint/repair boundaries. | Revert provider prompt/mapping changes independently; V0.1 run artifacts and release remain unchanged. |
| Phase 2 — unify evidence eligibility and human-selection contract | Define one versioned claim-eligibility helper for new Research/Angle/Script paths. Explicitly distinguish recommendation from recorded human angle selection. Test `verified`, basis, and `allowed_downstream` combinations plus legacy compatibility. | New workflow path can be disabled/reverted without rewriting old run artifacts or V0.1 release. |
| Phase 3 — second real economic case | Choose and document a different economic question/source package, then run the same production path without adding a case-specific branch. Validate provenance, facts, Research, angle selection, script, and audio gates with that case. | Keep the second run isolated; discard/revert its artifacts without touching Fed V0.1. |
| Phase 4 — reusable visual templates | Replace incidental numeric/string detection with typed, data-driven storyboard/visual objects. Add rendering fixtures for multiple metrics/topics and verify claim bindings and no text overflow. Preserve GDP calibration as a named compatibility path. | Revert the template owner while retaining existing rendered Fed media. |
| Phase 5 — word-level alignment evaluation | Evaluate WhisperX or another local alignment option as an optional adapter. Keep proportional sentence timing as an explicit fallback and compare audio/caption bounds on fixtures. No provider is required for tests. | Alignment adapter can be disabled; existing sentence-level timelines remain valid and accurately labeled. |

## 6. Definition of Done

V0.2 is complete when:

1. A second real economic case uses the same production pipeline without a topic-specific production branch.
2. Research, Angle, and Script share a clearly versioned fact-eligibility contract, including verification status and downstream permission.
3. Script generation cannot proceed from a system recommendation alone in the V0.2 workflow; an explicit human-selected angle is recorded.
4. The normal shared storyboard/video path contains no Fed/SEP/FOMC/GDP-specific semantic branches. Named legacy/calibration compatibility components may remain.
5. Source, fact, attribution, and scope references remain traceable through Research, Angle, Script, and the final video inputs.
6. V0.1.0 artifacts and public release remain unchanged; safe non-integration regression does not lose coverage or regress.
7. Limitations, including sentence-level proportional timing until a word-alignment adapter is validated, are described accurately.

## Next action

Phase 1A is complete. Review/authorize Phase 1B separately before changing content provider prompts or script behavior. Do not start Phase 1B automatically.
