# Current Handoff

## 当前交接 — V0.2 已验收，公开包装完成

**`V0.2_ACCEPTED` · Case 2 production COMPLETE · Human Final Video Review APPROVED**

截至 2026-10-02，BLS 第二真实案例已完成 canonical Final Render、immutable Final Candidate、独立 Final Video QA 与人工终审。正式验收记录在 [V0_2_ACCEPTANCE_REVIEW.md](../cases/bls-aug-2026-employment/V0_2_ACCEPTANCE_REVIEW.md)，视频审阅记录在 [FINAL_VIDEO_REVIEW.md](../cases/bls-aug-2026-employment/FINAL_VIDEO_REVIEW.md)。下面的 Phase 3C.6A / 3C.5 等记录描述当时状态，不再是当前下一步。

- 当前分支：`v0.2/generalize-video-workflow`；验收基线 commit：`6a697d9c7d7790daf1da2fd0b02d6460487900bb`。包装前与远端同分支同步，相对 `main` 为 ahead 47 / behind 0；包装 commit 仅在本地，具体 HEAD 以 Git 为准。
- BLS Final：58.710s、1080×1920、30 FPS、H.264/AAC、9 scenes、12 subtitle cues；SHA-256 `5167703eeb0dd1855c30c2012ad0f1a44dbbed6617f27231b34332f93c723cdd`。Final QA Attempt 2 为 PASSED、20/20，失败 Attempt 1 保留；人工终审 APPROVED。
- 最新已记录验证：相关 MP4/QA focused **57 passed**；safe non-integration **1018 passed、3 skipped、0 failures/errors**。3 个 renderer-level 配置相关 skips 不算通过，不包含 integration suite。
- [README](../README.md) 已展示 Fed/BLS 两案例、V0.2 门禁、真实测试边界与当前限制。docs 路径在本次环境可正常安全写入，当前状态已同步；此前 deferred 记录仍保留在历史审计材料中。
- V0.1.0 Fed Release 保持冻结且公开；BLS 视频仍是本地 ignored 产物，尚未合并、tag、创建 V0.2 Release 或发布 BLS 媒体。本次没有 push。

**Exact next action：人工决定是否将包装完成的 V0.2 分支合并到 main。** 之后再单独决定 `v0.2.0` tag、Release 和 BLS asset 发布；本次验收和包装不授权这些操作。准备清单见 [RELEASE_READINESS.md](v0.2/RELEASE_READINESS.md)。

## Historical Phase 3C.6A — Final Render contract ready, export not started

以下为当时的阶段记录，后续 Final Render、QA 和人工终审已完成；其中的 pending / not started 不代表当前状态。

**`V0.2_PHASE_3C6A_READY_FOR_FINAL_RENDER`**

已按用户既有决定记录 Preview Candidate 3 的 `approved_for_final_render`，reviewer 为 `motty63-ctrl`，时间 `2026-09-30T10:22:16+08:00`。本阶段没有再次请求审批，也没有启动 HyperFrames / FFmpeg、LLM、TTS 或外部服务。

| 当前正式 artifact | SHA-256 / state |
|---|---|
| `runs/2026-09-27-001-bls-august-2026-employment-situation/human_preview_review_candidate_3.json` | `9a746fe7dbfe6ff872dfaf1f11a98eabab3f80f7a0387fb9c18f8e8c2a954c55` · valid/current |
| `runs/2026-09-27-001-bls-august-2026-employment-situation/final_render_request.json` | `1f5ea05edaadfb96bad0285382ed06fed671f22846f3db52781f012732a40269` · validated/current |
| `runs/2026-09-27-001-bls-august-2026-employment-situation/render_manifest_final.json` | `ac70d8cd628e54aa14dc77ebdefe8bd82fec055cc7a528523cacff39a72a7703` · valid/current, ready_for_final_render |
| `runs/2026-09-27-001-bls-august-2026-employment-situation/renderer_project_final` | `b073d8cef8d50c4bb1b7f443adfabcf2b3773579912c9b20ddafc5d846572d1d` · valid/current |
| `runs/2026-09-27-001-bls-august-2026-employment-situation/final.mp4` / `final_video_candidate.json` | missing — not generated |

Approval 绑定当前 Preview 3、Timeline 2、Visual Candidate 3、音频、Script、recovered Storyboard、两条字幕身份、timing refinement、上游审批和 renderer package/manifest 的完整 hash 链。决策记录的 `final_render_approved=true` 只有在 owner 重新验证完整 current 依赖后才可授权 export；stale approval 不能继续授权。旧 `changes_required` / `approved_for_review` 仍是非最终渲染批准。

通用实现 commit：`e9b11c9379d882d52a46e3b1cf31e8afee0cd180`。新 owner APIs：`create_final_render_request()` → `validate_final_render_request()` → `prepare_final_render()`；后续真实 export 才可调用 `record_final_video_candidate()`。未注册的 source preview 不能仅凭文件存在或技术 QA 获得最终渲染许可。

独立 final manifest 为 `preview_only=false`、`full_render_requested=true`。Final package 复制获批 renderer package 的原始 bytes，保留当前 composition、审阅标识、字幕、motion 和时钟行为；没有改写 Preview 3 manifest 或 Timeline 2。配置来自 pinned HyperFrames package 与既有 canvas/timing metadata：HyperFrames `0.8.20`、1080×1920、30 FPS、native H.264/AAC MP4 export profile，继承 renderer default quality，不增加 bitrate 策略。

Final Render 未开始，Final Candidate 未生成。未来 candidate 的 contract 状态为 `pending_human_final_review`，technical QA / Human Final Video Review / workflow acceptance 是分别待完成的 gate；技术产物或最终视频审批都不自动代表 V0.2 acceptance。没有发布、上传、Release/tag、push 或 merge；V0.1.0 保持冻结。

验证：focused **81 passed**；safe non-integration **990 passed, 0 failed, 0 skipped**，包括已安装本地浏览器上的 renderer 回归。新增直接回归保证 dependency map 键顺序不影响批准身份；采用唯一 review/media 直接依赖对识别授权 candidate。独立 review 未发现其余 blocker。新生产代码无 BLS/case ID、claim_063–071、当前数值/hash/timestamp 专用分支。`git diff --check` 通过。

Offline replay 审计：184 个原 run 文件中，183 个内容文件 byte-identical，仅 owner 更新 `run.json`。原 Script、音频、Storyboard、Visual 3、Facts、Research、Timeline 2、Preview 1/2/3 与历史 reviews 均保持不变。Ignored run artifacts 按既有约定保留在本地，没有 force-add 二进制或 run 输出。

**Exact next phase: Phase 3C.6B — Canonical Final Render + Final Media QA。** 使用上述 current approved request/manifest 与不变的 Timeline 2，完成真实 export、decode / actual-frame / subtitle / Preview→Final QA 后，停在人工 Final Video Review；本阶段没有执行这一步。

**FINAL RENDER = NOT STARTED · HUMAN FINAL VIDEO REVIEW = NOT STARTED · V0.2 ACCEPTANCE = PENDING**

## Historical Phase 3C.5C — corrected preview review checkpoint

**`V0.2_PHASE_3C5C_WAITING_FOR_PREVIEW_REVIEW` · `HUMAN PREVIEW REVIEW = PENDING`**

Preview Candidate 1 has the explicit human `CHANGES_REQUIRED / SUBTITLE_OCCLUSION_AND_TIMING_SYNC` decision. Preview Candidate 2 is `TECHNICAL_RENDER_FAILURE / RENDER_TIME_AND_SUBTITLE_LAYOUT`, never registered for human review; it is not a human rejection. Both videos and old renderer packages are preserved.

Generic renderer fix `0e587cc` binds scenes, motion and captions to requested HyperFrames frame time, independently of audio playback. Full subtitle text is measured after browser font resolution; compact panels adapt to actual wrapping and safe free bands without clipping or covering measured critical objects/footers. No BLS/Fed-specific rendering branches or added font files are used.

The formal owner reused Timeline Candidate 2 unchanged (SHA-256 `3e60ff14724751cef59d252e013c76950db37cacc30f99f515aa4e1db9da6642`) and generated renderer/preview Candidate 3. All previously existing run files except owner-updated `run.json` remain byte-identical. Current MP4: `runs/2026-09-27-001-bls-august-2026-employment-situation/review-preview-candidate-3.mp4`; SHA-256 `0421363e620e56429e8b14b3dead33b5fbdbf99f1b0eda1ecece917b9738f4fe`. It is NON-FINAL, 3,889,121 bytes, 1080×1920, 30 FPS, H.264/AAC, 58.700 s video / 58.679 s audio.

Actual QA covered 9 scene interiors, 6 boundary frames, all 12 subtitle cues, and opening/ending. The 27 scene/boundary/cue frames match the compiled DOM; scene_003 is correct and scene_008's three lines are visible. Both DOM probes report zero clipping/footer/critical-object collision. Focused tests: 49 passed; safe non-integration: 958 passed (zero failures/skips); diff check passed. Font fallback and large-HTML lint messages remain documented non-blocking limitations. Timing remains pause-refined sentence timing, not word-level forced alignment.

**Exact next action: human review of Preview Candidate 3 and `cases/bls-aug-2026-employment/PREVIEW_REVIEW.md`.** No preview approval, final render, publication, push, merge, or V0.2 completion is authorized by this phase.

## Historical V0.2 status through Phase 3C.5

- V0.1.0 remains frozen and public; its Fed demo and Release are unchanged.
- Active development branch: `v0.2/generalize-video-workflow`.
- Phases 1A, 1B, 1C, 2A, 2B, 3A.1, 3A.2, 3B.1, 3B.2, and 3C.1.2–3C.1.5 are complete. Earlier Phase 3C.1 / 3C.1.1 failures remain historical checkpoints; their validation gaps were addressed by later generic work.
- BLS Phase 3A human review approved the Facts/Research package for Angle Planning; five candidates passed the documented checks and the user selected `angle_001`. The current Script remains human-approved for TTS with its original hash-bound approval. Phase 3C.2B changed neither Script nor Facts/Research/angle/terminology content.
- **Historical Phase 3C.5 checkpoint: `PHASE_3C5_WAITING_FOR_PREVIEW_REVIEW`; its gate: `HUMAN PREVIEW REVIEW = PENDING`.** Audio Candidate 2 is approved for Storyboard. The recovered Storyboard remains approved through its hash-bound record; Visual Candidate 1 and Candidate 2 retain their formal `CHANGES_REQUIRED` reviews. Candidate 3 bundle SHA-256 `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355` was explicitly approved for Timeline by `motty63-ctrl`; the review is bound to the recovered Storyboard and current upstream hashes. The formal Timeline owner generated a 5.1 composition with 9/9 scenes, 12 subtitle cues, and the unchanged 58,679 ms audio. A local `PREVIEW · NOT FINAL` renderer project is ready for human inspection; no final video render/export occurred. Alignment remains estimated proportional sentence timing. See [PREVIEW_REVIEW.md](../cases/bls-aug-2026-employment/PREVIEW_REVIEW.md), [CASE_STATE.md](../cases/bls-aug-2026-employment/CASE_STATE.md), [VISUAL_REVIEW.md](../cases/bls-aug-2026-employment/VISUAL_REVIEW.md), and [AUDIO_REVIEW.md](../cases/bls-aug-2026-employment/AUDIO_REVIEW.md).
- Phase 1B generalizes DeepSeek script generation and repair plus deterministic mock script generation; its remaining topic-specific mapping is isolated to a historical Fed V0.1 compatibility adapter.
- Phase 3A/3B for the BLS run produced five eligible angles from the current verified package; four of five Research Focus dimensions have direct eligible support, while survey-boundary support remains omitted. The user selected `angle_001`; the hash-bound selection and terminology artifacts remain current. The earlier `GENERALIZATION_GAP` is a historical checkpoint resolved by generic extraction work, with no BLS-specific production branch.
- Phase 3A.2 focused tests passed 90 and the safe non-integration regression passed 729 at that checkpoint. These are historical phase results, not the current audio-focused test result.
- The BLS run is `2026-09-27-001-bls-august-2026-employment-situation`. Candidate 2 is current against the approved Script and narration inputs. Human audio approval SHA-256 is `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f`; alignment SHA-256 is `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306`; subtitle SHA-256 is `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46`.
- **Historical Phase 3C.5 next action (superseded above): human preview review** using [PREVIEW_REVIEW.md](../cases/bls-aug-2026-employment/PREVIEW_REVIEW.md) and `runs/2026-09-27-001-bls-august-2026-employment-situation/renderer_project/review-preview.html`. Review pacing, motion, subtitle/audio sync, legibility, scene continuity, and ending. Do not approve a final render or export from this packet; a separate human decision is required.
- Phase 2 and V0.2 are not complete. The Fed V0.1 run and public Release remain untouched. See [docs/v0.2/GENERALIZATION_PLAN.md](v0.2/GENERALIZATION_PLAN.md).

## Current public release

- The V0.1.0 Fed Case 2 Video MVP is implemented on `main` and has been pushed to the public repository: <https://github.com/motty63-ctrl/fenglei-economy-content-engine>.
- GitHub Release `v0.1.0` is published at <https://github.com/motty63-ctrl/fenglei-economy-content-engine/releases/tag/v0.1.0>; its `final.mp4` asset is public. The verified file SHA-256 is `8796c73d62bed1090a9bbf6af268f5b91406b36913954d944953955d157c564d`.
- The V0.1.0 implementation and release are public project state. The active V0.2 branch is a development branch based on the public `main` snapshot above; read actual Git state for its current HEAD and ahead/behind.

## Fed Case 2 status

Run: `2026-09-24-001-fed-sep-case-2-source-inventory` under `runs/2026-09-24-001-fed-sep-case-2-source-inventory/`.

The native Case 2 run and video MVP are complete. The run has the approved four-document Federal Reserve source package, reviewed publication dates, native Facts 2.2, the locked `research_focus.json` and current Research, five eligible angles, user-selected `angle_001`, an evidence-grounded script, human-approved Volcengine narration, sentence-level proportional timing, an eight-scene visual plan, and the verified MP4. See `docs/FED_CASE_2_DEMO.md` for the record.

The final video is `runs/2026-09-24-001-fed-sep-case-2-source-inventory/final.mp4`, approximately 74.633 seconds, 1080×1920, 30 FPS, H.264/AAC. Caption timing is proportional to normalized sentence length; it is not WhisperX word-level forced alignment.

No new Fed approved checkpoint was created, imported, or promoted. The original historical Fed checkpoint remains blocked by `ANGLE_FORMAL_FIELDS_MISSING`; it was not repaired, upgraded, reused, imported, or promoted. The source package's independent source count remains `1`, and its legacy `selection_status` remains `insufficient_sources`.

## Historical checkpoint boundary

The old checkpoint recovery remains closed. Do not repair, backfill, infer, default, copy, or upgrade its missing `AngleCandidate` fields. GDP artifacts and test fixtures are not valid Fed recovery sources.

## Handoff boundary

当前停止在 **V0.2_ACCEPTED → PUBLIC PACKAGING → HUMAN MERGE DECISION**。人工最终视频批准与工作流验收均已记录，公开包装只修改 README / 状态文档。不得把验收视为 merge、push、tag、Release 或媒体发布授权。历史失败候选、拒绝记录和旧 blocked Fed checkpoint 保留；不得修复或升级旧 checkpoint。
