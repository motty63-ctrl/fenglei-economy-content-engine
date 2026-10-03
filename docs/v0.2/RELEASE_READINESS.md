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

当前分支：`main`；PR #2 于 2026-10-03 合并，原 V0.2 head 为 `0b1f9c253236ff121f63ab01b09ed979b8746a64`，开发分支保留。验收基线 `6a697d9c7d7790daf1da2fd0b02d6460487900bb` 保留为历史身份；本次 post-merge 文档 commit 仅在本地。实际 HEAD / ahead-behind 请读 Git，不将历史 hash 当成当前 HEAD。

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

技术验证引用最新已记录 MP4/QA focused **57 passed**、safe non-integration **1018 passed / 3 skipped / 0 failures/errors**。三个 renderer-level 配置相关 skips 未当作已通过，integration suite 不在此数字中。本阶段仅改文档，无需重复全量测试。

## GitHub metadata 建议（未修改设置）

本轮提供的 repository description 为 `AI-powered economic explainer video workflow for Fenglei`，topics 与 LICENSE 均无。本清单记录建议，不声称重新查询远端，也不修改 GitHub 设置。

- Description 可保留；若更新，可用：`Evidence-grounded economic video workflow with auditable human gates — Fenglei`。
- 建议 topics：`ai`、`python`、`workflow`、`content-pipeline`、`video-generation`、`fact-checking`、`human-in-the-loop`、`economics`、`llm`、`ffmpeg`。
- 缺少 LICENSE 不是本次 merge blocker；公开可见不等于已授予开源复用许可。许可证应由维护者根据代码、依赖及媒体权益有意选择，本阶段不自动添加。

## 发布描述须保留的边界

当前是经两个真实案例验证的工作流，不是任意主题的一键自动生产系统。计时为 pause-refined sentence-level，不是 word-level forced alignment；视觉为 static SVG + programmatic motion；在线服务和媒体工具需配置。规则验证与人工审核共同控制事实范围，不宣称通用自动语义证明。终审、验收、合并和公开发布是不同决定。

下一步仅为 **V0.2.0 Release Packaging**。PR #2 的 main 合并已完成；本次文档协调没有 push、创建 tag / Release、BLS asset upload 或媒体重新生成。
