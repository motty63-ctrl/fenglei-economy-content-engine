# BLS August 2026 — Angle Review (Phase 3B.2)

## 审查边界

- Case：`bls-aug-2026-employment`
- Run：`2026-09-27-001-bls-august-2026-employment-situation`
- 锁定问题：2026 年 8 月美国就业报告中，非农就业、失业率、工资和工时发生了什么变化？6 月与 7 月非农就业数据被如何修正，哪些行业对 8 月就业变化贡献较大或形成拖累？
- Facts SHA-256：`f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`
- Research SHA-256：`ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862`
- Research Focus SHA-256：`fe638d26622e271951365188f9fe0ba0b474ee2fb3bde3c544e0e91f4098b32a`
- Phase 3A approval SHA-256：`696db2972f7d1683ae2e79249ba4e883ca303666746bedd8cf2c273aedb213b0`
- 新 angles SHA-256：`32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8`

本轮使用正式离线 angle-generation owner 和本地 `MockContentPlanningProvider`，在 `stop_after="angle_generation"` 停止。Facts、Research、Research Focus、sources、source index 和 approval 均保持原 hash；没有生成 selection、Script 或媒体。

## 候选集覆盖概览

Planner 将 Research Focus 拆为五个问题维度：

| 维度 | 有支持 claim | 本候选集处理 |
|---|---|---|
| `focus_001`：非农 payroll 与失业率 | `claim_063`、`claim_064` | 覆盖 |
| `focus_002`：平均时薪与平均每周工时 | `claim_065`、`claim_066` | 覆盖 |
| `focus_003`：6 月、7 月修订及此前发布值边界 | `claim_067`、`claim_068` | 覆盖 |
| `focus_004`：报告明确描述的行业变化 | `claim_069`–`claim_071` | 覆盖；仍是部分行业例证 |
| `focus_005`：Household / Establishment Survey 边界及当前、此前、修订值区分 | 无符合资格的直接 claim | 明确未覆盖，不据结构信息自行补结论 |

本组候选共使用全部九条已核验且允许下游使用的 claims（`claim_063`–`claim_071`）；没有 eligible claim 被规划器遗漏。每个维度的“覆盖”表示至少有映射的事实，不代表穷尽该维度。行业证据仅包括两项报告为增加的行业和一项报告为下降的行业，不构成完整行业排名。调查口径维度保持未覆盖，因为当前 eligible claims 没有直接回答该边界问题。

当前 `core_insight` 保存对应的逐字 evidence excerpts，便于人工追溯；它不是完成润色的口播叙事。人工选择时仍需判断该视角是否适合短视频表达，以及后续 Script 能否在不扩大证据范围的前提下形成清晰叙事。

## 候选审查

### `angle_001` — 从已核验记录看核心问题的几个部分

- **一句话思路：**把当前有证据支持的四个问题维度并列呈现，并明确没有回答调查口径边界问题。
- **开场 hook：**当前证据能直接回答核心问题的哪些部分？
- **核心问题：**围绕当前研究问题，现有已核验记录分别支持哪些范围？
- **Supporting claims：**`claim_063`、`claim_064`、`claim_065`、`claim_066`、`claim_067`、`claim_068`、`claim_069`、`claim_070`、`claim_071`。
- **覆盖维度：**`focus_001` 非农 payroll 与失业率；`focus_002` 时薪与工时；`focus_003` 6 月和 7 月修订；`focus_004` 行业例证。
- **有意省略：**`focus_005` 调查口径及当前/此前/修订值边界。
- **支持密度：**0.444（4 个映射维度 / 9 条 supporting claims）；Research Focus coverage ratio 为 0.8（4/5）。
- **Authority safety：**通过；`eligible`，无 rejection code。
- **Editorial quality：**通过；当前标题和 hook 未触发未支持维度检查。
- **已知限制：**它是覆盖面最广的候选，但不是对锁定问题的完整回答。后续叙述必须将 Household Survey 失业率与 Establishment Survey 指标分开，并保留行业证据仅为部分例证的限制；不可补写调查边界结论或因果关系。

### `angle_002` — 分类记录里有哪些具体变化？

- **一句话思路：**仅呈现报告中有直接 eligible evidence 支持的行业变化例子。
- **开场 hook：**报告提到的行业变化有哪些？
- **核心问题：**哪些分类记录有直接证据支持？
- **Supporting claims：**`claim_069`、`claim_070`、`claim_071`。
- **覆盖维度：**`focus_004` 报告明确描述的行业变化。
- **有意省略：**`focus_001`、`focus_002`、`focus_003`、`focus_005`。
- **支持密度：**0.333（1 个映射维度 / 3 条 supporting claims）；coverage ratio 为 0.2（1/5）。
- **Authority safety：**通过；`eligible`，无 rejection code。
- **Editorial quality：**通过；使用“具体变化”与“有直接证据支持”的有限范围表述。
- **已知限制：**行业材料是部分覆盖，仅支持若干已记录例子（两项增加、一项下降），不能说成全行业排名、最大行业或完整分解。

### `angle_003` — 同一报告的不同栏目，各自记录什么？

- **一句话思路：**并列检查非农就业记录和失业率记录，同时保留它们来自不同统计栏目这一事实。
- **开场 hook：**不同栏目各记录了什么？
- **核心问题：**同一报告的不同栏目各自记录了什么？
- **Supporting claims：**`claim_063`、`claim_064`。
- **覆盖维度：**`focus_001` 非农 payroll 与失业率。
- **有意省略：**`focus_002`、`focus_003`、`focus_004`、`focus_005`。
- **支持密度：**0.5（1 个映射维度 / 2 条 supporting claims）；coverage ratio 为 0.2（1/5）。
- **Authority safety：**通过；`eligible`，无 rejection code。
- **Editorial quality：**通过；候选聚焦于栏目差异，没有声称两类调查结果可以互相解释。
- **已知限制：**两个指标属于不同调查口径，后续必须明确区分 Household Survey 与 Establishment Survey；本候选本身不回答更广泛的调查方法问题。

### `angle_004` — 两项指标，分别有哪些已核验读数？

- **一句话思路：**将已核验的平均时薪与平均每周工时分项展示，不把二者写成因果关系。
- **开场 hook：**两项指标各自记录了什么？
- **核心问题：**现有记录分别支持关于这些指标的哪些描述？
- **Supporting claims：**`claim_065`、`claim_066`。
- **覆盖维度：**`focus_002` 平均时薪与平均每周工时。
- **有意省略：**`focus_001`、`focus_003`、`focus_004`、`focus_005`。
- **支持密度：**0.5（1 个映射维度 / 2 条 supporting claims）；coverage ratio 为 0.2（1/5）。
- **Authority safety：**通过；`eligible`，无 rejection code。
- **Editorial quality：**通过；标题和 hook 保持为并列指标观察。
- **已知限制：**两条记录来自 Establishment Survey；只能按各自的口径转述，不能暗示工资变化导致工时变化。

### `angle_005` — 原始估计与后续修订，分开核对

- **一句话思路：**把 6 月和 7 月的前次估计、修订后数值及修订幅度作为历史修订记录分开讲清。
- **开场 hook：**前次估计与修订值如何对应？
- **核心问题：**历史估计的修订前后数值如何对应？
- **Supporting claims：**`claim_067`、`claim_068`。
- **覆盖维度：**`focus_003` 6 月与 7 月 payroll revisions。
- **有意省略：**`focus_001`、`focus_002`、`focus_004`、`focus_005`。
- **支持密度：**0.5（1 个映射维度 / 2 条 supporting claims）；coverage ratio 为 0.2（1/5）。
- **Authority safety：**通过；`eligible`，无 rejection code。
- **Editorial quality：**通过；以修订记录为窄主题。
- **已知限制：**修订幅度不是对应月份当期就业变化。不得把修订记录改写成新的月度 payroll 增量，也不得推断修订原因。

## 系统推荐

- **recommended_angle_id：**`angle_001`
- **总分：**87
- **基础评分：**64（evidence strength 3、audience relevance 4、novelty 3、hook strength 3、visual potential 3、explainability 3、controversy risk 0）
- **覆盖奖励：**16（0.8 × 20）
- **支持密度奖励：**2（0.444 × 4，四舍五入）
- **范围对齐奖励：**5
- **候选冗余惩罚：**0
- **支持信息：**9 条 claims、4/5 Research Focus 维度；支持密度 0.444。
- **候选集差异：**5 个候选的 support set、覆盖维度或 framing 结构有实质差异；候选集 diversity gate 通过。

**系统推荐 ≠ 人工选择。**推荐是可审计的确定性启发式结果，不表示它是“最佳”角度，也不构成人工批准。当前没有 `angle_selection.json`；本轮没有选择任何候选。现有 Human Angle Gate 会在调用 Script provider 前要求有效的人类选择；`test_v02_script_entry_requires_human_selection_before_provider_calls` 在本轮 focused suite 中通过。

## 人工选择入口与下游边界

如果人工审阅后决定继续，可通过正式 CLI 明确记录选择：

```powershell
.venv\Scripts\python.exe -m fanglei --runs-dir runs select-angle 2026-09-27-001-bls-august-2026-employment-situation --angle-id angle_00X --reviewer motty63-ctrl --rationale "填写真实选择理由"
```

将 `angle_00X` 替换为人工实际选择的 ID，并填写真实理由。本报告没有执行该命令。Script、TTS/audio、storyboard、timeline 和 rendering 均未运行。
