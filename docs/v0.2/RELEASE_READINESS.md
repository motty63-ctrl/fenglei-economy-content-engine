# V0.2 合并与发布准备

本清单记录已完成的 main 合并及后续发布准备，不是 push、tag、Release 或 upload 授权。当前品牌：**风雷经济内容引擎 / Fenglei Economy Content Engine**。

## 准备结论

| 项目 | 结论 | 依据与边界 |
|---|---|---|
| V0.2 acceptance | ACCEPTED | [验收报告](../../cases/bls-aug-2026-employment/V0_2_ACCEPTANCE_REVIEW.md)：第二真实案例、通用生产链路、独立 QA、人工终审已完成 |
| Branch merge to main | COMPLETE | [PR #2](https://github.com/motty63-ctrl/fenglei-economy-content-engine/pull/2) 已以 Create a merge commit 合并；merge commit：`ee4c20c0eb0317a94ef09856afa2c1ecd63d185c` |
| v0.2.0 Release | READY WITH ACTIONS | 尚无 tag 或 Release；需决定版本目标、发布文案与 asset 范围 |
| BLS MP4 release asset | NOT PUBLISHED | 当前仅在 local ignored run；最终视频批准不自动授权公开上传 |
| Docs reconciliation | COMPLETE | post-merge 当前状态已同步；旧阶段记录保留并标为历史 |
| README | UPDATED | 两案例、V0.2 workflow、main 已合并、真实测试结果和未发布边界均已呈现 |
| V0.1.0 | FROZEN / UNCHANGED | [既有 Fed Release](https://github.com/motty63-ctrl/fenglei-economy-content-engine/releases/tag/v0.1.0) 保留，不移动 tag 或修改 asset |

当前分支：`main`；PR #2 于 2026-10-03 合并，原 V0.2 head 为 `0b1f9c253236ff121f63ab01b09ed979b8746a64`，开发分支保留。验收基线 `6a697d9c7d7790daf1da2fd0b02d6460487900bb` 保留为历史身份；post-merge 文档基线 `dbcdacd66d004b8c495d8a7ca3dceccadccaf1ac` 已同步到 origin/main。实际 HEAD / ahead-behind 请读 Git，不将历史 hash 当成当前 HEAD。

## 发布前的最小动作

1. 决定 BLS 视频的公开展示方式。
2. 决定原样发布 accepted Final，还是创建去除审阅标签的 publication-only copy。现有审阅标签属于已接受的媒体状态，不是 V0.2 acceptance 问题；发布形式是独立决定。
3. 如制作 publication copy，执行独立 publication-media QA；不得修改或替换 accepted Final Media / Candidate。
4. 准备并单独批准 `v0.2.0` tag target 与中文 Release notes；保留 V0.1.0 历史。
5. 仅上传显式获批的 release assets，并核验实际上传文件的 SHA-256。
6. Release 真实存在后，才将 `v0.2.0` Release 链接补入 README；不能提前创建假链接。

BLS accepted Final：58.710s、1080×1920、30 FPS、H.264/AAC、9 scenes、12 cues；QA Attempt 2 为 20/20 PASSED，人工终审 APPROVED。文件 SHA-256：

```text
5167703eeb0dd1855c30c2012ad0f1a44dbbed6617f27231b34332f93c723cdd
```

Accepted Final Candidate SHA-256：`52f901cabf73ccee056a98d4a062c4412c2e82703e553ec01f66a81c4a386a93`。两项身份保持冻结，本次不修改或重渲染媒体。

验收阶段的历史技术验证为 MP4/QA focused **57 passed**、safe non-integration **1018 passed / 3 skipped / 0 failures/errors**。三个 renderer-level 配置相关 skips 未当作已通过，integration suite 不在此数字中；这些是 acceptance 基线，不是发布基础设施变更后的测试数。

## Release Infrastructure Phase A2

main 已合并、V0.2 已 accepted；本阶段仅实现发布准备能力，不重新执行真实案例 Final QA，不制作 publication media，不创建 tag / Release 或上传。

### QA 身份与历史审批

必须分别判断 artifact dependency currentness、历史 QA execution identity、当前 QA implementation identity。实现升级不等于媒体依赖变化。

- 原 `final-video-qa/1.0`、`final-video-qa/1.1` 原样解析；其隐式 implementation contract 为 `final-video-qa-implementation/1.0`。已有 digest 保留，1.0 report 未记录 digest 时实现状态为 `unknown`。
- 新执行输出 `final-video-qa/1.2`（owner 1.2），包含 `final-video-qa-implementation/2.0` 身份及参与文件清单；不改写旧 report。
- V2 参与文件按顺序为 `src/fanglei/final_video_qa.py`、`src/fanglei/final_video_probe.mjs`。身份中的路径相对于 `src/fanglei/`。各 UTF-8 source bytes 只做 CRLF → LF、CR → LF；保留其他字节、空白、注释、Unicode 和末尾换行。
- 聚合 body 为 `implementation_contract_version` 与有序 `sources` 数组；每行包含 `relative_source_path`、`canonical_source_sha256`。使用 UTF-8、sorted keys、无多余分隔空白的 JSON，再计算 SHA-256。digest 自身不在 body 中；不依赖 Git、绝对路径、mtime 或用户名。
- `derive_final_video_qa_status()` 只判内容依赖及 QA 结果；`derive_final_video_qa_implementation_status()` 单独报告 `current / superseded / unknown`。
- 现有审批通过 `validate_existing_human_final_video_approval()` 验证精确 Candidate、Media、Request、bound QA SHA 与依赖。只升级 QA 代码不能撤销已有批准。
- 新审批仍由 `validate_human_final_video_review_entry()` 开门，要求 passed、依赖 current 且 implementation current；superseded / unknown QA 不可开启新审批。

真实案例的历史 Attempt 2：**PASSED / dependencies current / implementation superseded**。其 SHA 仍为 `ab520249af764b3f8823bee8aea066e22b152309785e06379205ca4acb1746ce`；Human Final Approval 仍有效，SHA 仍为 `3605deaa54caa24d5048fe5e8dce0b96c853b52741489661253beeb9b23fa910`。Attempt 1、Attempt 2、Final Candidate、Final Media、Human Approval 和 accepted acceptance 记录均冻结。

### 通用 presentation mode 与独立 package

`review_composition_html(..., presentation_mode="review")` 默认为 review，保持原输出。显式 publication 只移除 owner 定义的 `PREVIEW · NOT FINAL` 与 `HUMAN REVIEW REQUIRED` overlay 节点。未知 mode、缺失/重复/变形 overlay fail closed；不根据 case、文件名或 `preview_only` 猜 mode。

正式离线 owner：

```python
prepare_publication_renderer_package(
    run_dir,
    presentation_mode="publication",
    expected_candidate_sha256=accepted_candidate_hash,
    expected_approval_sha256=existing_approval_hash,
)
validate_publication_renderer_package(run_dir)
```

owner 消费有效的既有 Final Approval（允许其 historical QA superseded），绑定 Final Candidate、Media、Request、QA、Timeline、Visual、Subtitle、Audio、Storyboard、Script 和原 renderer。复制 accepted `renderer_project_final` 到独立 `renderer_project_publication`，只移除 entry HTML 的两个 overlay；所有其他文件及 entry 的剩余字节相同。包括字幕文字/位置/时序、source footer、scene 顺序/数字、motion、audio、canvas/FPS 都不能改变。

`publication_renderer_package.json` 使用 `publication-renderer-package/1.0`，状态为 `ready_for_publication_render`，**不是上传、发布或 Release 审批**。`qa_implementation_status` 是准备时的审计观察值，不是历史内容依赖。readonly validator 同时验证 registry、binding 与实际 package 的唯一授权差异。

registry 只新增独立下游 package 节点；依赖从 accepted Final / existing approval / production inputs 指向 publication，不反向指向 Final。上游变化使 package stale/reject；publication 改动不会 stale accepted Final history，DAG 无环。真实 run 本阶段尚未调用此 owner。

**下一阶段：V0.2.0 Publication Render → Publication QA → Human Publication Review。** Publication QA 必须采用 current 实现，独立记录；不能复用历史 Final QA 作为 publication QA。尚无 Publication MP4 / Publication QA / Human Publication Approval，也没有 v0.2.0 tag / Release / upload。

### A2 验证停止点

Release Infra implementation 已通过验证，可进入 Publication Render 阶段。验证确认此前 28 个 importer/source-capture failures 属于 `ENVIRONMENT_PATH_LENGTH`：首个历史失败测试在短 basetemp 下通过，source-cache 路径由 260 字符缩短为 229 字符；其后完整 safe non-integration suite 通过，期间没有修改 production 或 test code。

- Focused：**106 passed / 3 skipped**。synthetic media QA 已实际执行；3 个 skips 是 `tests/test_preview_renderer.py` 要求显式配置本机 browser/Node/HyperFrames runtime。
- 短 basetemp safe non-integration：**1055 passed / 3 skipped / 0 failures / 0 errors**。此前长 basetemp 的 28 个失败均未复现。
- `git diff --check` 通过。Production hardcoding audit 未发现案例专用分支或当前 BLS identity；包含 publication nodes 的 registry graph 为 **74 nodes / acyclic**。
- 历史 Final QA Attempt 2 保持 immutable，结果为 **passed / superseded / dependency-valid**；既有 Human Final Approval 仍有效。新的审批仍要求当前 QA implementation identity。
- Generic `presentation_mode`、独立 publication package owner 和 registry artifact 已实现。默认 `review` 保留两个 review overlays；显式 `publication` 仅移除这两个 overlays。accepted Final、Candidate、Media、QA history 和 Human Approval 保持冻结。
- 本阶段没有生成 Publication MP4、没有重跑真实 BLS Final QA，也没有创建 tag / Release 或上传媒体。
- 实现与文档将分为两个本地 commits；当前尚未提交，也未 push。

**下一阶段：V0.2.0 Publication Render → Publication QA → Human Publication Review。**

## Release Infrastructure Phase B — 通用 Publication lifecycle

通用发布媒体基础设施已实现并通过验证。Publication 是已接受 Final 的单向下游副本，不是新的 Final Candidate，也不会改变 Final Candidate、Final Media、Final QA 或 Human Final Approval。

- `publication-render-request/1.0` 将 publication package、renderer package、Accepted Final Candidate/Media、Human Final Approval、Final Render Request、画布/帧率/renderer 配置、媒体工具链 lock hash 和输出目标绑定在一起。输出只接受显式输入的 `release/<version>/<asset>.mp4`；Final、Preview、路径逃逸和已有输出文件均 fail closed。
- 独立 Publication Render owner 先验证 package、Final 授权链、request、工具链与 manifest，再将渲染写入临时文件并一次性注册 Publication Media。媒体记录保存文件 SHA、长度、Publication/Final 来源身份与技术参数；媒体文件和 `publication_media.json` 均为独立注册物，重复写入会被拒绝。
- `publication-video-qa/1.0` 是独立 QA owner，按 immutable attempt 记录结果，失败历史保留；它验证容器和完整音视频解码、格式/时长/帧数、场景/字幕、音频等价、source footer、开头结尾、字幕布局与溢出、黑帧、overlay 去除及 Accepted Final → Publication 的区域比较。当前唯一授权差异为 `review_overlay_removal`；比较区域从 source renderer composition 的 review-overlay 节点计算，并记录实际渲染帧的像素比较结果。
- Human Publication Review 入口只在 Publication Media、当前 QA attempt、package/request 和 Accepted Final 授权链均 current 且 QA passed 时开放。review record 需要显式人工提供 `approved_for_release` 或 `changes_required`；它不记录 `published` / `released`。
- ArtifactRegistry 的 publication 分支只依赖已接受 Final 与 publication 上游；Final 图中没有反向 publication 依赖。当前启用 Publication 模式的 registry 为 **79 nodes / acyclic**；request 指定唯一输出路径后会增加该媒体路径节点（80 nodes）。最终 graph 也由 synthetic DAG 测试覆盖。
- Publication render / QA / human review 的逻辑使用 synthetic run 与 renderer/measurement stubs 验证。Focused：**65 passed**。短 basetemp safe non-integration regression：**1083 passed / 18 skipped / 0 failures / 0 errors**。跳过项为本机 Node/Chromium/HyperFrames 条件式 renderer/media 测试；integration suite 未纳入。

当前真实 BLS run 的 publication renderer package 保持 `ready_for_publication_render`，但 **Phase B 未运行真实 Publication Render、未生成 Publication QA 或 Human Publication Review**。复核时 Accepted Final SHA 仍为 `5167703eeb0dd1855c30c2012ad0f1a44dbbed6617f27231b34332f93c723cdd`，Candidate SHA 为 `52f901cabf73ccee056a98d4a062c4412c2e82703e553ec01f66a81c4a386a93`，Final QA Attempt 2 和 Human Final Approval 也保持原 hash。没有创建 tag / GitHub Release 或上传媒体。

**下一阶段：V0.2.0 BLS Publication Render → Publication QA → Human Publication Review。**

## GitHub metadata 建议（未修改设置）

本轮提供的 repository description 为 `AI-powered economic explainer video workflow for Fenglei`，topics 与 LICENSE 均无。本清单记录建议，不声称重新查询远端，也不修改 GitHub 设置。

- Description 可保留；若更新，可用：`Evidence-grounded economic video workflow with auditable human gates — Fenglei`。
- 建议 topics：`ai`、`python`、`workflow`、`content-pipeline`、`video-generation`、`fact-checking`、`human-in-the-loop`、`economics`、`llm`、`ffmpeg`。
- 缺少 LICENSE 不是本次 merge blocker；公开可见不等于已授予开源复用许可。许可证应由维护者根据代码、依赖及媒体权益有意选择，本阶段不自动添加。

## 发布描述须保留的边界

当前是经两个真实案例验证的工作流，不是任意主题的一键自动生产系统。计时为 pause-refined sentence-level，不是 word-level forced alignment；视觉为 static SVG + programmatic motion；在线服务和媒体工具需配置。规则验证与人工审核共同控制事实范围，不宣称通用自动语义证明。终审、验收、合并和公开发布是不同决定。

当前下一步仅为 **V0.2.0 BLS Publication Render → Publication QA → Human Publication Review**。人工发布审核完成后，再单独进入 V0.2.0 Release Packaging。PR #2 的 main 合并已完成；本阶段没有 push、创建 tag / Release、BLS asset upload 或真实 publication media 生成。
