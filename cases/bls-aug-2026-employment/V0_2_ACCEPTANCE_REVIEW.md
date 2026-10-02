# V0.2 工作流验收 — 第二真实案例 BLS August 2026 Employment Situation

**V0.2_ACCEPTED · Human Final Video Review APPROVED · Case 2 production COMPLETE**

这份记录依照用户指定的 A–L 条件审计通用工作流。视频审批与工作流验收分别记录；验收不授权 merge、push、tag、Release、upload 或发布。

## A. 正式最终视频批准

- Reviewer：`motty63-ctrl`；scope：**V0.2 Case 2 final video**。
- 人工终审时间：`2026-10-02T10:34:32.323781Z`。
- 正式 owner：`fanglei.final_video_qa.record_human_final_video_review(...)`；先重新验证当前 Candidate、latest passed QA 与完整依赖，再记录用户已明确给出的决定。
- 正式 run artifact：`runs/2026-09-27-001-bls-august-2026-employment-situation/human_final_video_review.json`。
- [FINAL_VIDEO_APPROVAL.json](FINAL_VIDEO_APPROVAL.json) 是该正式记录的逐字节 Git 审计副本，SHA：`3605deaa54caa24d5048fe5e8dce0b96c853b52741489661253beeb9b23fa910`；不是另一套审批体系。
- 当前 Candidate SHA：`52f901cabf73ccee056a98d4a062c4412c2e82703e553ec01f66a81c4a386a93`。
- Final Media SHA：`5167703eeb0dd1855c30c2012ad0f1a44dbbed6617f27231b34332f93c723cdd`。
- QA Attempt 1：FAILED，SHA `f59839e21966de3901121c71147b32b32669ac306f0652d5f0c4ac0100783a01`。旧 MP4 probe 把有效 ISO-BMFF 结构误判，原报告仍保留。
- 当前 QA Attempt 2：PASSED、20/20，SHA `ab520249af764b3f8823bee8aea066e22b152309785e06379205ca4acb1746ce`。previous_qa 显式绑定 Attempt 1。

本轮未 rerender、未重跑 QA、未修改任何 media/candidate 或其他历史决定。209 个既有 run 内容文件（不含可变 `run.json`）均保持原 bytes/hash，仅追加正式终审记录并由 owner 更新 manifest。Candidate 本体中的 `pending` 字段是不可变创建快照；当前批准状态来自独立的 `human_final_video_review.json`，不得覆写 Candidate 以改成 approved。

## B. V0.2 目标与两个真实案例

验收问题：**是否在第二个真实经济案例上证明可复用的经济短视频制作工作流，且不需要案例专用 production branch？**

- **Case 1 / Fed**：`fed-sep-revisions`，run `2026-09-24-001-fed-sep-case-2-source-inventory`。它是冻结的 V0.1.0 第一个真实 Video MVP 和 legacy 兼容参考，官方 Fed package、participant SEP comparison 与 Committee statement 保持区分。74.633s、8 scenes、12 captions。当前本地 final SHA `8796c73d62bed1090a9bbf6af268f5b91406b36913954d944953955d157c564d` 与 [既有 Demo 记录](../../docs/FED_CASE_2_DEMO.md) 一致。旧 blocked checkpoint 不因本验收获修复或 promotion。
- **Case 2 / BLS**：`bls-aug-2026-employment`，run `2026-09-27-001-bls-august-2026-employment-situation`。使用真实 BLS August 2026 release 与 July archive 的批准 local captures，并非 Fed fixture replay。Source package `13680d96d487497ed19d95ecbd09ccbf213e732f6787dc066320e11ed44355d9`；independent count 仍为 1，legacy selection status 仍为 insufficient_sources。Native Facts 2.2：71 claims、9 verified、1 conflicted、61 unverified；下游只使用 9 条 eligible facts。

BLS 官方 URL：`https://www.bls.gov/news.release/empsit.htm` 与 `https://www.bls.gov/news.release/archives/empsit_08072026.htm`。本轮核验的是批准的 local capture/provenance，不重新访问可变 live 页面。

实际链路：Facts → Research Focus → Research → Angle Candidates → Human Selection → Script → Human Script Approval → TTS → Human Audio Approval → Storyboard → Human Storyboard Approval → Visual Assets → Human Visual Approval → Timeline → Preview → Human Preview Approval → Final Render → Final Video QA → Human Final Video Approval。

BLS Final：3,579,255 bytes；1080×1920、30 FPS、1761 frames、H.264/AAC；container 58.710s、video 58.700s、audio 58.688s。9/9 scenes、12/12 cues 的现有 QA 均 passed；Scene 003、Scene 008、三个关键场景边界、opening/ending 与 approved Preview 3 无已检测的 material divergence。像素相似性是 normalized RGB difference 指标，不称作 SSIM，也不声称有限帧采样证明每帧完全相同。

## C. A–L 验收结果

| 条件 | 结果 | 当前证据 |
|---|---|---|
| A — 第二真实案例 | PASS | BLS August 2026 Employment Situation 的两份获批官方 capture，Facts 2.2 共 71 条、9 verified；case/run/source 身份均不同于 Fed。 |
| B — 正式端到端完成 | PASS | canonical FinalRenderRequest、复制的获批 renderer package、已登记 Final Media/Candidate、QA Attempt 2 与正式人工终审形成连续 current 链。 |
| C — 无 BLS 专用生产分支 | PASS | src 的文本及 Python 解码字符串审计无 BLS、case ID、claim_063–071、当前数据/hash/timestamp 专用逻辑；数值、roles 和 ID 仅作为输入。 |
| D — 通用人工门禁 | PASS | Angle、术语、Script、Audio、Storyboard、Visual、Preview、Final 均有显式人工记录与 hash/依赖绑定；采用 opt-in V0.2 路径，不宣称 legacy API 一律强制同样门禁。 |
| E — 通用事实安全 | PASS | 共享 eligibility、atomic proposition、attribution/scope、数字和 revision role 验证、facts-hash-bound 术语；Research/Script 仅使用 9 条 eligible claims。 |
| F — 媒体依赖图 | PASS | 实际 registry 72 个节点无环；正式终审含 56 个传递上游，所有 current，相关上游变化经依赖 hash 使下游 stale。 |
| G — 独立 Final QA | PASS | QA 与 Candidate 分离；失败 Attempt 1、passed Attempt 2 及 previous_qa 链保留；latest current passed 才能打开终审，Candidate bytes 不变。 |
| H — Legacy / Case 1 兼容 | PASS | 已验证代码自 da7b855 后没有生产/test/tool 改动，复用 1018 passed / 3 skipped；Fed final SHA 与 V0.1 文档一致。 |
| I — 无未解案例绕过 | PASS | 下列 13 项 blocker 已以通用修复、环境解锁或显式人工决定关闭，没有 BLS 专用代码 workaround。 |
| J — 可审计与复核 | PASS | 关键产物、hash、dependency、reviewer、决定与时间可追溯；原 Storyboard、3 个 Visual/Preview、Audio 1、两次 Final QA 保留；旧失败 Script hash 由 human_script_edit 绑定。 |
| K — 测试充分性 | CAUTION | 最新 57 focused、1018 passed / 3 skipped；本轮 6 passed / 10 deselected 的 owner/失效/写入门禁 focused。3 个 renderer-level 工具配置测试未运行，不当作已通过。 |
| L — 已知限制 | PASS | 以下限制明确接受为 V0.2 边界，不要求该阶段新增产品能力或公开发布。 |

判定规则：A–J 全部 PASS；K 为 PASS 或非阻塞 CAUTION；L 无 BLOCKS_V0.2_ACCEPTANCE。当前满足规则，因此 **V0.2 ACCEPTANCE = ACCEPTED**。

## D. 完整 blocker-resolution 表

| 历史问题 | 最终分类 | 通用 owner / implementation | 解决边界 |
|---|---|---|---|
| cross-language terminology | GENERIC_FIX | src/fanglei/script_terminology.py / src/fanglei/script_lint.py | 显式 human-approved、Facts-hash-bound 术语，不以 heuristic 猜译；40 approved、6 numeric entries rejected。 |
| authority validation | GENERIC_FIX | src/fanglei/authority_safety.py / src/fanglei/evidence_targets.py | atomic proposition 与独立 scope 一致，保留完整 evidence provenance；不放行邻接未验证子句。 |
| duration target semantics | GENERIC_FIX | src/fanglei/script_lint.py / src/fanglei/content_models.py | editorial target 与硬区间分开；target miss 是 warning，实际音频时长成为媒体时钟。 |
| target-language identity | GENERIC_FIX | src/fanglei/providers/content.py / src/fanglei/content_pipeline.py | 规范 target_language 显式绑定，冲突拒绝；不是由案例名称决定语言。 |
| TTS number pronunciation | GENERIC_FIX | src/fanglei/narration_normalization.py / src/fanglei/providers/narration.py | 通用 zh-CN 数值口语投影、独立 narration 身份，approved Script 不变；Audio 1 不佳结果和 review 保留。 |
| storyboard timing binding | GENERIC_FIX | src/fanglei/visual_models.py / src/fanglei/visual_pipeline.py | 消费 approved audio/alignment/subtitle/selection、scene 时间范围和 segment 绑定；估算精度明确。 |
| visual hierarchy recovery | HUMAN_DECISION | src/fanglei/human_storyboard_recovery.py / src/fanglei/human_visual_asset_recovery.py / src/fanglei/visual_assets.py | 人工视觉编辑通过通用 visual-only owner 与移动端排版校验；不修改 facts/timing/claims。 |
| subtitle/timing refinement | GENERIC_FIX | src/fanglei/playback_preview.py / src/fanglei/preview_composition.py | 批准音频派生 pause-refined sentence timing、cue panel/line-wrap，不生成事实、不更换音频。 |
| renderer time authority | GENERIC_FIX | src/fanglei/nikola_adapter.py / src/fanglei/preview_composition.py | render 时钟显式 seek，渲染字幕跟随 timeline；修复场景边界和 Scene 003 regression。 |
| Final Render approval contract | GENERIC_FIX | src/fanglei/final_render.py / src/fanglei/playback_preview.py | approved_for_final_render、hash-bound Request、独立 final branch；preview approval 不自动等于发布。 |
| Final Video QA contract | GENERIC_FIX | src/fanglei/final_video_qa.py / src/fanglei/artifact_registry.py | immutable Candidate + independent QA + hash-bound Human Final Review，最新 passed/current attempt 门禁。 |
| MP4 compatibility | GENERIC_FIX | src/fanglei/final_video_probe.mjs / src/fanglei/final_video_qa.py | 标准 ISO-BMFF 结构兼容；技术属性用显式 ffprobe，独立浏览器 decode / frame comparison 不弱化。 |
| FFmpeg executable environment | ENVIRONMENT_ONLY | tools/ffmpeg/package.json / tools/ffmpeg/package-lock.json / tools/ffmpeg/README.md | 项目本地显式 executable 路径与 child-process 配置；没有系统 PATH 或 BLS production 改动。 |

没有 UNRESOLVED 的案例专用 workaround。人工提供脚本、视觉编辑和最终审批是正式工作流输入，不等于 BLS 专用生产逻辑。该案例不是完全无人参与的内容生成演示。

## E. 保留限制

- **ACCEPTED_V0.2_LIMITATION** — pause-refined sentence timing，不是 WhisperX word-level forced alignment；时间精度仍是估算。
- **ACCEPTED_V0.2_LIMITATION** — 静态 SVG + programmatic motion；不是动态影像或通用创意语义证明。
- **ACCEPTED_V0.2_LIMITATION** — docs/ 更新 DEFERRED_REPARSE_POINT_ENVIRONMENT，仍有 Phase 3C.6A 当前状态待安全环境统一。
- **ACCEPTED_V0.2_LIMITATION** — 项目本地 FFmpeg 2018 build / ffprobe 4.0.2 与 Node/Chromium；工具路径需配置，不保证任意机器直接运行。
- **ACCEPTED_V0.2_LIMITATION** — BLS final.mp4 仍在 ignored runs/ 本地，V0.2 未 merge/push/tag/release/upload。
- **ACCEPTED_V0.2_LIMITATION** — FinalRenderRequest/Final Candidate/QA 有正式 Python owners；完整编码通过 pinned HyperFrames 与显式工具配置，没有统一 final-MP4 CLI / 完整更新 runbook。
- **ACCEPTED_V0.2_LIMITATION** — 本次批准对象保留 Preview 的 PREVIEW · NOT FINAL / HUMAN REVIEW REQUIRED 画面标签；本阶段媒体冻结，终审状态以独立 approval 为准。
- **ACCEPTED_V0.2_LIMITATION** — 限定结构/词汇的 fail-closed 校验不是任意自然语言蕴含证明；内容表达和视觉恢复仍需要人工。
- **ACCEPTED_V0.2_LIMITATION** — 旧失败 Script 由 failed_draft_sha256、阶段/commit 历史和人工 recovery 记录追溯；未宣称所有原始 provider responses 均可逐字重放。
- **ACCEPTED_V0.2_LIMITATION** — BLS 行业覆盖是两个增加与一个下降的已验证子集，不是完整行业排名或宏观因果结论。

这些限制不阻塞本轮工作流验收，也不授权本轮修复或进入 V0.3。公开包装、画面 review 标签和统一 CLI/runbook 应在后续人工整合/发布决策时处理，不能声称已经准备好无需配置的一键重放。

## F. 测试与代码冻结证据

- 最新通用 MP4/QA focused：**57 passed**，来自 Phase 3C.6B3。
- 最新 safe non-integration：**1018 passed、3 skipped、0 failures/errors**。已验证 generic code commit：`da7b855ad2777983a5febdb33e1bad734e40d421`。
- 本轮 focused：**6 passed、10 deselected**，38.48s。实际覆盖显式 QA-bound human final owner、QA write-once/Candidate immutability、media/request/preview approval 改动失效、blocking failure 禁止标为 passed。
- 三个历史 skips 位于 `tests/test_preview_renderer.py:82,91,101`，需要显式 renderer-level 工具配置；不是全部 integration/renderer 测试已经运行的声明。
- `git diff da7b855..d3808a5 -- src tests tools pyproject.toml` 为空，本轮没有 production/test/tool 代码改动。遵照用户要求不仪式性重跑全量回归。
- 本轮额外执行验收 JSON 结构、时区时间、criteria 判定、所有绑定 hash/currentness、负向审计样本及 media freeze 验证；该 case 级记录不增加 runtime gate。

## G. 通用安全 / 人工门禁 / DAG

Search、Research Focus、Script provider、Storyboard/Visual 的普通路径已使用结构化输入；V0.2 eligibility 共享 `verified AND allowed_downstream is True`，缺失/无效状态 fail closed。Authority safety 继续检查 attribution、atomic scope、structured numeric/revision roles 和已批准术语。未借 authority package 产生 independent corroboration。

当前 source 文本与 Python 解码常量审计未发现 BLS、case ID、claim_063–071、当前数值/hash/timestamp 专用分支。历史 Fed attribution aliases、明确标记的 GDP calibration 和 legacy adapters 是兼容表，不因此宣称自然语言校验已适用于任意经济领域。

Angle selection、术语、Script、Audio、Storyboard、Visual、Preview、Final 人工决定分别由正式 owner/contract 记录。相关 upstream hash 变化令后续 artifact stale。这个结论针对 opt-in V0.2 生产链；没有声称 legacy/default 所有 API 都强制等待全部新审批。

当前 registry **72 nodes、acyclic**。Final review 本体依赖 Candidate 和 QA Attempt 2；Candidate/QA/Request 的传递闭包有 **56 个 current upstream artifacts**，含完整 script/audio/storyboard/visual/timeline/subtitle/preview 身份与审批。QA 不修改 Candidate，不形成 candidate → QA → candidate 循环。失败 QA 仍是 valid historical artifact；technical result failed 与 registry freshness valid 是不同维度。

## H. 正式身份 / 哈希快照

以下均由本轮 registry/currentness 检查读取，不从文件名或 case 名推断：

| Artifact（相对于 run） | SHA-256 | State |
|---|---|---|
| `facts.json` | `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882` | valid/current |
| `research_focus.json` | `fe638d26622e271951365188f9fe0ba0b474ee2fb3bde3c544e0e91f4098b32a` | valid/current |
| `research.md` | `ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862` | valid/current |
| `angles.json` | `32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8` | valid/current |
| `angle_selection.json` | `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77` | valid/current |
| `script_terminology.json` | `a9ee561650535b58d3c6f5bb36c30a884225f70c202f6f0923e2954f05262d2c` | valid/current |
| `script.json` | `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` | valid/current |
| `human_script_approval.json` | `8653415689546d56295f857722840de61f14d26515d836f077a1a13818e3c59f` | valid/current |
| `audio/narration.wav` | `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183` | valid/current |
| `audio/review.json` | `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f` | valid/current |
| `human_storyboard_candidate.json` | `920299f4a2e483c5a6aeaeb2afaaa884cdd1a3c04b9c0b1c8d5bd3ca2cc5e7f3` | valid/current |
| `human_storyboard_approval.json` | `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05` | valid/current |
| `visual_assets_candidate_3` | `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355` | valid/current |
| `human_visual_asset_review_candidate_3.json` | `a92d5d010c2ae2389ca8cd8c85da3bb5614dfaae684326e2e3390505004c11b3` | valid/current |
| `alignment.json` | `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306` | valid/current |
| `subtitle_track.json` | `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46` | valid/current |
| `playback_timing_refinement.json` | `e007fb6a112a0c05f0a6ec5b7147975d3cf76ce3a14965db46e06e5f752581a3` | valid/current |
| `preview_subtitle_track_candidate_2.json` | `bc872a3255594871210f0edf28d0842c0128a2a9d2cb0977f667153d1a0cca20` | valid/current |
| `timeline_candidate_2.json` | `3e60ff14724751cef59d252e013c76950db37cacc30f99f515aa4e1db9da6642` | valid/current |
| `review-preview-candidate-3.mp4` | `0421363e620e56429e8b14b3dead33b5fbdbf99f1b0eda1ecece917b9738f4fe` | valid/current |
| `human_preview_review_candidate_3.json` | `9a746fe7dbfe6ff872dfaf1f11a98eabab3f80f7a0387fb9c18f8e8c2a954c55` | valid/current |
| `final_render_request.json` | `1f5ea05edaadfb96bad0285382ed06fed671f22846f3db52781f012732a40269` | valid/current |
| `render_manifest_final.json` | `ac70d8cd628e54aa14dc77ebdefe8bd82fec055cc7a528523cacff39a72a7703` | valid/current |
| `renderer_project_final` | `b073d8cef8d50c4bb1b7f443adfabcf2b3773579912c9b20ddafc5d846572d1d` | valid/current |
| `final.mp4` | `5167703eeb0dd1855c30c2012ad0f1a44dbbed6617f27231b34332f93c723cdd` | valid/current |
| `final_video_candidate.json` | `52f901cabf73ccee056a98d4a062c4412c2e82703e553ec01f66a81c4a386a93` | valid/current |
| `final_video_qa.json` | `f59839e21966de3901121c71147b32b32669ac306f0652d5f0c4ac0100783a01` | valid/current |
| `final_video_qa_attempt_2.json` | `ab520249af764b3f8823bee8aea066e22b152309785e06379205ca4acb1746ce` | valid/current |
| `human_final_video_review.json` | `3605deaa54caa24d5048fe5e8dce0b96c853b52741489661253beeb9b23fa910` | valid/current |

Recovered Storyboard canonical SHA 另为 `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`；它与文件 bytes SHA 是不同哈希对象。

完整闭包及每个 dependency hash 保存在 [V0_2_ACCEPTANCE.json](V0_2_ACCEPTANCE.json)。该 `workflow-acceptance-review/1.0` 是 case-level、machine-readable audit snapshot，不是新 pipeline approval system 或发布授权；发生依赖/代码变化后必须重新检查。Accepted reviewer：`motty63-ctrl`；audit actor：Codex；accepted_at：`2026-10-02T10:39:17.210928+00:00`。Acceptance JSON SHA：`e5360ced3bbfc1c54f19d731a991152074239830879216b6cd1c7c0a1e8fe4de`。

Script failed_draft SHA 在 human recovery record 中保留；Audio Candidate 1、原 Storyboard/review、Visual Candidate 1/2/3 的决定与 bundle、Preview 1/2/3、Final QA 1/2 均保持历史。没有声称所有 provider 原始响应都已形成完整 immutable attempt archive。

## I. 当前状态与人工下一步

- Case 2 Final Video：APPROVED；Case 2 production：COMPLETE；V0.2 workflow acceptance：ACCEPTED。
- `docs/`：**DEFERRED_REPARSE_POINT_ENVIRONMENT**。PROJECT_STATE、CURRENT_HANDOFF 和 GENERALIZATION_PLAN 的 reconciliation 留待安全写入环境；本轮未绕过 safeguards。
- Branch：`v0.2/generalize-video-workflow`；本轮仅本地 case/acceptance commit。
- Final 本地未发布；没有 merge、push、tag、Release、upload 或 publication。V0.1.0 保持冻结。
- 推荐下一步：人工决定是否整合分支，以及是否准备 V0.2 Release；先在安全环境核对 deferred project docs、公开资产包装与发布范围。不要自动执行。
