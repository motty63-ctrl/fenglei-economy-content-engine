# BLS August 2026 — Angle Review

## 审查边界

- Case：`bls-aug-2026-employment`
- Run：`2026-09-27-001-bls-august-2026-employment-situation`
- Locked question：2026 年 8 月美国就业报告中，非农就业、失业率、工资和工时发生了什么变化？6 月与 7 月非农就业数据被如何修正，哪些行业对 8 月就业变化贡献较大或形成拖累？
- Facts：`facts.json` SHA-256 `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`
- Research：`research.md` SHA-256 `ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862`
- Research Focus：`research_focus.json` SHA-256 `fe638d26622e271951365188f9fe0ba0b474ee2fb3bde3c544e0e91f4098b32a`
- 人工审核记录：`PHASE3A_APPROVAL.json` SHA-256 `696db2972f7d1683ae2e79249ba4e883ca303666746bedd8cf2c273aedb213b0`，授权范围仅为把列明的九条 Facts 和当前 Research 用于 Angle Planning。
- Angles：`angles.json` SHA-256 `b897f1eaca70ce4bd3b7482fd9304ecead3e1eb9930609c4ea39467bdbc70afb`

五个候选均由正式离线 Angle Planning owner 生成，状态为 `eligible`，没有 rejection code。Authority safety 对每个候选的支持 claim 均通过：使用已核验的原子 proposition，保留 BLS attribution，未把完整 evidence span 中未核验的邻近句扩展为内容。以下逐项说明候选实际覆盖面；候选文字按 `angles.json` 原样记录，不代表人工选择。

## 候选审查

### `angle_001` — 把已核验记录并排看

- **Hook：**这些记录能回答哪些问题，又有哪些边界？
- **核心问题：**2026 年 8 月美国就业报告中，非农就业、失业率、工资和工时发生了什么变化？6 月与 7 月非农就业数据被如何修正，哪些行业对 8 月就业变化贡献较大或形成拖累？
- **核心内容与支持 claims：**
  - `claim_063` — “U.S. Bureau of Labor Statistics: ‘Total nonfarm payroll employment increased by 162,000 in August’”
  - `claim_064` — “U.S. Bureau of Labor Statistics: ‘The unemployment rate was unchanged at 4.1 percent in August’”
  - `claim_065` — “In August, average hourly earnings for all employees on private nonfarm payrolls rose by 10 cents, or 0.3 percent, to $37.75.”（capture 在 `10` 与 `cents` 之间有换行。）
  - `claim_066` — “The average workweek for all employees on private nonfarm payrolls edged up by 0.1 hour to 34.4 hours in August.”（capture 在 `to` 与 `34.4` 之间有换行。）
  - `claim_067` — “The change in total nonfarm payroll employment for June was revised up by 11,000, from +20,000 to +31,000”（capture 在 `from` 与 `+20,000` 之间有换行。）
- **覆盖：**非农就业、失业率、工资、工时和 6 月修订有支持；7 月修订、行业变化没有列入该候选支持 claims。与锁定问题相比为部分覆盖。
- **与其他候选的区别：**五条不同维度的记录并列呈现，是候选中覆盖面最广的总览结构。
- **刻意省略：**不纳入 `claim_068`（7 月修订）及 `claim_069`–`claim_071`（行业变化）；不对未纳入的部分作答。
- **局限：**核心问题比支持材料范围宽，尤其提到了 7 月修订和行业贡献。若继续制作，必须把内容收窄到实际支持的五条记录，不能暗示完整回答锁定问题。

### `angle_002` — total nonfarm payroll employment：先看一项记录

- **Hook：**这一项记录的范围和变化，具体是什么？
- **核心问题：**BLS 的 2026 年 8 月 Employment Situation 对非农 payroll employment 和失业率分别报告了什么变化？
- **核心内容与支持 claims：**
  - `claim_063` — “U.S. Bureau of Labor Statistics: ‘Total nonfarm payroll employment increased by 162,000 in August’”
- **覆盖：**非农就业有直接支持。核心问题虽写到失业率，但候选没有把 `claim_064` 列为支持 claim，因此失业率部分目前没有候选内的事实支持。
- **与其他候选的区别：**将注意力缩到单一非农 payroll 记录，而不是多指标总览或证据边界比较。
- **刻意省略：**失业率、工资、工时、修订和行业变化均不进入该候选的 factual content。
- **局限：**问题措辞涵盖了未列入支持范围的失业率。若选中，制作时需把问题缩到 payroll 单项，或先由正式 owner 重新生成具备相应支持 claim 的候选；不得在脚本阶段自行添入数字。

### `angle_003` — 不同证据各自能说明什么

- **Hook：**不同类型的正式记录，分别能支持哪类表述？
- **核心问题：**如何保留 household survey 与 establishment survey 的统计边界，并区分当前月估计、此前发布值和修订值？
- **核心内容与支持 claims：**
  - `claim_064` — “U.S. Bureau of Labor Statistics: ‘The unemployment rate was unchanged at 4.1 percent in August’”
- **覆盖：**失业率这项 Household Survey 记录有支持；候选没有提供 Establishment Survey、此前发布值或修订值的支持 claim，所以跨调查/跨版本比较只是问题提出的方向，尚无足够候选事实支撑。
- **与其他候选的区别：**以调查和证据类型的区分作为观察角度；当前唯一列出的事实仍仅为 Household Survey 失业率。
- **刻意省略：**不声称两类调查结果相互解释，也不陈述任何修订数值。
- **局限：**作为候选问题，它比一条失业率事实更广。若选择，叙述须限于该已支持记录，不能暗示已经完成调查体系或修订比较。

### `angle_004` — 原文记载与解释之间的边界

- **Hook：**哪些内容是文件直接写明的？
- **核心问题：**BLS 的 2026 年 8 月 Employment Situation 对非农 payroll employment 和失业率分别报告了什么变化？
- **核心内容与支持 claims：**
  - `claim_063` — “U.S. Bureau of Labor Statistics: \"Total nonfarm payroll employment increased by 162,000 in August\"”
  - `claim_064` — “U.S. Bureau of Labor Statistics: \"The unemployment rate was unchanged at 4.1 percent in August\"”
- **覆盖：**支持两条分别归因于 BLS 的 8 月记录；相对于锁定问题，只覆盖非农就业和失业率，不覆盖工资、工时、修订或行业变化。
- **与其他候选的区别：**聚焦原文能够直接证明什么，以及应停在哪条解释边界；只使用两条独立归因的原子命题。
- **刻意省略：**不在两条事实之间建立因果，不据此推断整体就业趋势、经济衰退或政策含义。
- **局限：**两条数据属于不同调查口径：非农就业来自 Establishment Survey，失业率来自 Household Survey。后续必须清楚分开呈现，不能合并成同一统计总体或暗示二者可直接互相解释。

### `angle_005` — 从记录到结论，证据边界在哪里

- **Hook：**直接记载到哪一步，解释又从哪里开始？
- **核心问题：**How can the records be presented together without adding an unsupported explanation?
- **核心内容与支持 claims：**
  - `claim_071` — “U.S. Bureau of Labor Statistics: ‘Information employment declined by 23,000 in August’”
- **覆盖：**仅支持信息业 8 月就业下降这一项 Establishment Survey 记录；不能代表整体行业表现，也不能代表行业排名。
- **与其他候选的区别：**用一个行业下降个案讨论证据边界，不把它扩成整体就业概览或行业排序。
- **刻意省略：**不包括其他行业、不声称信息业变化造成总体变化，也不推断下降原因。
- **局限：**核心问题是一般性的证据边界问题，唯一支持事实是一个行业单项；制作时不可把它扩写成宏观结论或行业普遍趋势。

## 支持范围矩阵

| 候选 | 非农就业 | 失业率 | 工资 | 工时 | 6 月修订 | 7 月修订 | 行业变化 | 相对锁定问题 |
|---|---|---|---|---|---|---|---|---|
| `angle_001` | 完整 | 完整 | 完整 | 完整 | 完整 | 无 | 无 | 部分；问题范围明显超过支持 claims |
| `angle_002` | 完整 | 无 | 无 | 无 | 无 | 无 | 无 | 部分；核心问题提到未支持的失业率 |
| `angle_003` | 无 | 部分（仅失业率记录） | 无 | 无 | 无 | 无 | 无 | 部分；调查边界和修订比较未获候选 claims 支持 |
| `angle_004` | 完整 | 完整 | 无 | 无 | 无 | 无 | 无 | 部分；覆盖范围清晰且有限 |
| `angle_005` | 无 | 无 | 无 | 无 | 无 | 无 | 部分（仅信息业下降） | 部分；不能代表行业整体或总体就业 |

“完整”只表示该候选列出的具体 claim 有支持，不表示锁定问题该维度的全部可能分析均已覆盖。

## 事实安全检查

状态含义：`OK` 表示当前候选文字和支持关系未见该类越界；`CAUTION` 表示后续制作有明确边界需保持；`BLOCK` 表示当前不应按现有表述推进。它们是工作流安全标记，不是编辑质量排名。

| 候选 | 调查口径混淆 | 修订值混淆 | 行业过度概括 | 未支持因果 | Authority scope 扩张 |
|---|---|---|---|---|---|
| `angle_001` | CAUTION — Household 与 Establishment 指标需分开展示 | CAUTION — 仅有 6 月修订 claim；不得补写 7 月 | CAUTION — 核心问题提及行业，但该候选未支持行业 claims | OK | OK — 当前支持内容仍为 BLS 归因的原子命题 |
| `angle_002` | CAUTION — 问题提到失业率，支持列表只有非农就业 | OK | OK | OK | OK |
| `angle_003` | CAUTION — 仅有 Household Survey 失业率 claim | CAUTION — 问题提到修订，但无修订 claim | OK | OK | OK |
| `angle_004` | CAUTION — 两个指标来自不同调查口径，必须明确区分 | OK | OK | OK | OK — 两项命题均保留 BLS 归因 |
| `angle_005` | OK | OK | CAUTION — 仅有信息业单项，不可概括为行业排名或总体情况 | OK | OK — 仅限被支持的行业命题 |

当前审核未发现需要 `BLOCK` 才能阻止候选 artifact 的问题；候选问题范围与支持 claims 之间的上述 `CAUTION` 仍须由人类选题者考虑。所有候选通过的是当前 authority/eligibility 机器门禁，不代表完整脚本语义已审查或获得批准。

## 系统推荐

系统推荐：`angle_004`，总分 `68`。分项为：evidence strength `3`、audience relevance `4`、novelty `3`、hook strength `3`、visual potential `3`、explainability `4`、controversy risk `0`。这些是离线规划器的确定性启发式分数，不是客观质量测量。

`系统推荐 ≠ 人工选择`。推荐不代表“最佳选择”，也不创建 `angle_selection.json`。是否选择 `angle_004` 或其他候选由人工决定；未选择前 Script 生成及修复保持阻断。

## 人工选择命令

人工决定候选后，可用以下正式 CLI 命令记录选择。将 `angle_00X` 替换为实际候选 ID，并将 rationale 改为真实选择理由；本报告没有执行该命令。

```powershell
.venv\Scripts\python.exe -m fanglei --runs-dir runs select-angle 2026-09-27-001-bls-august-2026-employment-situation --angle-id angle_00X --reviewer motty63-ctrl --rationale "Human-selected for the next stage"
```

该命令只记录 hash-bound 人工选题，不生成 Script。Script 生成、TTS/audio、storyboard、timeline 与 rendering 均未执行；它们须按各自 owner、输入、审批和配置要求依次进行。当前 `angle_selection.json`、`script.json`、`script.md`、audio、storyboard、timeline、video 均不存在于该 run。

## 下游就绪度（只读核查）

- **Human Selection：**正式 CLI owner 可用上面的命令记录选择；当前尚未执行。
- **Script：**当前被缺少 `angle_selection.json` 阻断。选题后可选择本地 mock provider；DeepSeek 路径需要配置 `DEEPSEEK_API_KEY` 环境变量。未检查或输出密钥值，也未调用 provider。
- **TTS / voice review：**依赖 Script 及正式 narration/audio owner；Volcengine 或 Azure 凭证、speaker 与 resource 配置需在环境中准备。生成音频后仍须按实际音频 hash 做人工 voice review/approval。本轮未检查凭证值或调用服务。
- **Storyboard / visual：**依赖已生成的 Script，并应使用该 Script 和 claim bindings 运行相应正式 owner；本轮未执行。
- **Alignment / timeline：**生产 alignment 需要 production audio、当前 voice approval、匹配的 audio hash/duration 和带固定模型 provenance 的 alignment provider。WhisperX adapter 还要求显式 `RUN_WHISPERX_ALIGNMENT=1`；当前尚无 audio 或 alignment。
- **Renderer：**RUNBOOK 说明现有 CLI 仅提供 renderer preparation/preflight，没有正式最终 MP4 render CLI 命令。完整渲染入口仍需在后续工程阶段确认；本轮未运行 renderer。
