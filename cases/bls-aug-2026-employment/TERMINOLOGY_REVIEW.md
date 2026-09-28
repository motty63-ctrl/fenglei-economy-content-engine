# BLS 术语人工审核记录

- Case ID：`bls-aug-2026-employment`
- Run ID：`2026-09-27-001-bls-august-2026-employment-situation`
- 当前 Facts SHA-256：`f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`
- 人工审阅人：`motty63-ctrl`
- 审阅时间：`2026-09-28T14:57:47+08:00`
- 目标语言：`zh-CN`
- 审核结果：**40 APPROVED / 6 REJECTED_AS_NON_TERMINOLOGY / 0 PENDING**
- 正式可信术语表：`runs/2026-09-27-001-bls-august-2026-employment-situation/script_terminology.json`
- 正式术语表 SHA-256：`a9ee561650535b58d3c6f5bb36c30a884225f70c202f6f0923e2954f05262d2c`

正式术语表只包含获批的语言映射。六条被排除项是结构化数值事实，记录为非术语决定但不进入可信术语映射；`claim_067` 和 `claim_068` 仍是已批准、可下游使用的事实。提案文件仍只是历史候选，不作为运行时信任来源。

## 决定明细

| ID | 英文原词 / 结构字段 | 语义角色 | Claim scope | 批准的中文术语 | 获批别名 | 审核说明 | Decision |
|---|---|---|---|---|---|---|---|
| `term_27391d541746` | added (`authority_attestation.scope.certainty`) | `direction` | claim_070 | 新增 | 增加 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_fa163349e957` | declined (`authority_attestation.scope.certainty`) | `direction` | claim_071 | 减少 | 下降 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_039e74be1921` | edged up (`authority_attestation.scope.certainty`) | `direction` | claim_066 | 小幅上升 | 小幅增加 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_0ad79a906d3b` | increased (`authority_attestation.scope.certainty`) | `direction` | claim_063, claim_069 | 增加 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_1cf6e60facfd` | revised up (`authority_attestation.scope.certainty`) | `direction` | claim_067, claim_068 | 上修 | 向上修正 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_8049e91c4603` | rose (`authority_attestation.scope.certainty`) | `direction` | claim_065 | 上升 | 增加 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_93cbd650e380` | unchanged (`authority_attestation.scope.certainty`) | `direction` | claim_064 | 持平 | 保持不变 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_6706f06415f3` | up (`evidence.revision_values.direction`) | `direction` | claim_067, claim_068 | 上修 | 向上修正 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_a8efeac80fd5` | change (`authority_attestation.scope.measure`) | `metric` | claim_067, claim_068 | 变动 | 变化 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_d4ee78b1b15f` | employment (`authority_attestation.scope.measure`) | `metric` | claim_069, claim_071 | 就业人数 | 就业 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_3523b5fbb4b6` | hourly earnings (`authority_attestation.scope.measure`) | `metric` | claim_065 | 时薪 | 时薪收入 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_16399175a16b` | jobs (`authority_attestation.scope.measure`) | `metric` | claim_070 | 岗位数 | 就业岗位数、工作岗位数 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_4883a07f5088` | payroll employment (`authority_attestation.scope.measure`) | `metric` | claim_063 | 非农就业 | 非农就业人数 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_7f9bc81daac8` | unemployment rate (`authority_attestation.scope.measure`) | `metric` | claim_064 | 失业率 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_279a4b08ff53` | workweek (`authority_attestation.scope.measure`) | `metric` | claim_066 | 每周工时 | 工作周时长 | 指每周工时，不是工作日或排班安排。 | **APPROVED** |
| `term_1a9a7f53de5a` | August (`authority_attestation.scope.period`) | `period` | claim_063, claim_064, claim_065, claim_066, claim_069, claim_070, claim_071 | 8月 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_e98a88c97258` | July (`authority_attestation.scope.period`) | `period` | claim_068 | 7月 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_16239021dd74` | June (`authority_attestation.scope.period`) | `period` | claim_067 | 6月 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_5bb97b24c6d3` | Establishment Survey Data (`evidence.source_section`) | `reporting_scope` | claim_065, claim_066, claim_067, claim_068, claim_069, claim_070, claim_071 | 企业调查数据 | 企业调查 | 区分 Household / Establishment 调查；报告标题不是调查口径。 | **APPROVED** |
| `term_bb8f42a8a4c0` | Household Survey Data (`evidence.source_section`) | `reporting_scope` | claim_064 | 家庭调查数据 | 家庭调查 | 区分 Household / Establishment 调查；报告标题不是调查口径。 | **APPROVED** |
| `term_9b118cbc90e0` | THE EMPLOYMENT SITUATION - AUGUST 2026 (`evidence.source_section`) | `reporting_scope` | claim_063 | 2026年8月就业形势报告 | 8月就业报告、就业形势报告 | 区分 Household / Establishment 调查；报告标题不是调查口径。 | **APPROVED** |
| `term_1e20d23d221e` | 11,000 (`evidence.revision_values.revision_amount`) | `revision_delta` | claim_067 | — | — | 该数值属于结构化事实值，不是术语；通过 previous_value / revised_value / revision_amount / direction / period / unit 校验，禁止纳入术语映射。 | **REJECTED_AS_NON_TERMINOLOGY** |
| `term_f9219321f921` | 44,000 (`evidence.revision_values.revision_amount`) | `revision_delta` | claim_068 | — | — | 该数值属于结构化事实值，不是术语；通过 previous_value / revised_value / revision_amount / direction / period / unit 校验，禁止纳入术语映射。 | **REJECTED_AS_NON_TERMINOLOGY** |
| `term_87d4c94b741c` | +20,000 (`evidence.revision_values.previous_value`) | `revision_previous` | claim_067 | — | — | 该数值属于结构化事实值，不是术语；通过 previous_value / revised_value / revision_amount / direction / period / unit 校验，禁止纳入术语映射。 | **REJECTED_AS_NON_TERMINOLOGY** |
| `term_8985453d1b88` | -23,000 (`evidence.revision_values.previous_value`) | `revision_previous` | claim_068 | — | — | 该数值属于结构化事实值，不是术语；通过 previous_value / revised_value / revision_amount / direction / period / unit 校验，禁止纳入术语映射。 | **REJECTED_AS_NON_TERMINOLOGY** |
| `term_7686cf4dfee7` | +21,000 (`evidence.revision_values.revised_value`) | `revision_revised` | claim_068 | — | — | 该数值属于结构化事实值，不是术语；通过 previous_value / revised_value / revision_amount / direction / period / unit 校验，禁止纳入术语映射。 | **REJECTED_AS_NON_TERMINOLOGY** |
| `term_160e3366da8b` | +31,000 (`evidence.revision_values.revised_value`) | `revision_revised` | claim_067 | — | — | 该数值属于结构化事实值，不是术语；通过 previous_value / revised_value / revision_amount / direction / period / unit 校验，禁止纳入术语映射。 | **REJECTED_AS_NON_TERMINOLOGY** |
| `term_80d02c14e96e` | U.S. Bureau of Labor Statistics (`authority_attestation.attribution`) | `source_attribution` | claim_063, claim_064, claim_065, claim_066, claim_067, claim_068, claim_069, claim_070, claim_071 | 美国劳工统计局 | 美国劳工统计局（BLS）、BLS | 确认机构中文名及是否保留 BLS 缩写。 | **APPROVED** |
| `term_b2e339e34134` | July (`authority_attestation.scope.subject`) | `subject` | claim_068 | 7月 | — | 该字段是被修订月份，不是报告发布日期。 | **APPROVED** |
| `term_14174132408e` | June (`authority_attestation.scope.subject`) | `subject` | claim_067 | 6月 | — | 该字段是被修订月份，不是报告发布日期。 | **APPROVED** |
| `term_0496b858c0eb` | average hourly earnings (`authority_attestation.scope.subject`) | `subject` | claim_065 | 平均时薪 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_00064aba7f02` | average workweek (`authority_attestation.scope.subject`) | `subject` | claim_066 | 平均每周工时 | 平均工作周时长 | 指每周工时，不是工作日或排班安排。 | **APPROVED** |
| `term_f9efff7b3631` | food services and drinking places (`authority_attestation.scope.subject`) | `subject` | claim_069 | 餐饮服务和饮酒场所 | — | 确认中文覆盖原行业类别中的饮食场所范围。 | **APPROVED** |
| `term_3c677e754b4c` | information employment (`authority_attestation.scope.subject`) | `subject` | claim_071 | 信息业就业人数 | 信息业就业 | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_dcd86890f4a9` | local government education (`authority_attestation.scope.subject`) | `subject` | claim_070 | 地方政府教育部门 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_aa627b6a0fbf` | total nonfarm payroll employment (`authority_attestation.scope.subject`) | `subject` | claim_063 | 非农就业人数 | 非农就业、非农就业总人数 | 确认 total 与 payroll employment 口径，不缩窄为工资金额。 | **APPROVED** |
| `term_b73ea8039866` | unemployment rate (`authority_attestation.scope.subject`) | `subject` | claim_064 | 失业率 | — | 确认译法只覆盖字段含义并保留 claim 范围。 | **APPROVED** |
| `term_19262a1df4be` | $ (`authority_attestation.scope.unit`) | `unit` | claim_065 | 美元 | $ | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_d41a22d041aa` | hours (`authority_attestation.scope.unit`) | `unit` | claim_066 | 小时 | — | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_2fa106cf335a` | percent (`authority_attestation.scope.unit`) | `unit` | claim_064 | % | 百分比 | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_c814edabf40e` | $ (`evidence.explicit_values.unit`) | `unit` | claim_065 | 美元 | $ | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_ceea18e765c5` | cents (`evidence.explicit_values.unit`) | `unit` | claim_065 | 美分 | — | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_5b75f2f41c81` | hour (`evidence.explicit_values.unit`) | `unit` | claim_066 | 小时 | — | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_38f19a84c81a` | hours (`evidence.explicit_values.unit`) | `unit` | claim_066 | 小时 | — | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_f7fdd7a31244` | jobs (`evidence.explicit_values.unit`) | `unit` | claim_070 | 个岗位 | 岗位 | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |
| `term_d33a287a6ca4` | percent (`evidence.explicit_values.unit`) | `unit` | claim_064, claim_065 | % | 百分比 | 检查数值单位及紧邻数字的符号别名。 | **APPROVED** |

## 数值条目的明确排除决定

以下六项被标记为 `REJECTED_AS_NON_TERMINOLOGY`：`term_1e20d23d221e`、`term_f9219321f921`、`term_87d4c94b741c`、`term_8985453d1b88`、`term_7686cf4dfee7`、`term_160e3366da8b`。这是对术语映射资格的拒绝，不是对其底层事实的拒绝；数值与修订角色继续由 Facts 2.2 的结构化字段验证。

## 对应事实与 source context

### `claim_063`

- 原子 claim：U.S. Bureau of Labor Statistics: "Total nonfarm payroll employment increased by 162,000 in August"
- Scope：subject=`total nonfarm payroll employment`；measure=`payroll employment`；period=`August`；unit=`None`；certainty=`increased`
- Source context：`THE EMPLOYMENT SITUATION - AUGUST 2026` / `August nonfarm payroll employment change` / `registered exact evidence target`
- Exact evidence：`Total nonfarm payroll employment increased by 162,000 in August`

### `claim_064`

- 原子 claim：U.S. Bureau of Labor Statistics: "The unemployment rate was unchanged at 4.1 percent in August"
- Scope：subject=`unemployment rate`；measure=`unemployment rate`；period=`August`；unit=`percent`；certainty=`unchanged`
- Source context：`Household Survey Data` / `August unemployment rate` / `registered exact evidence target`
- Exact evidence：`The unemployment rate was unchanged at 4.1 percent in August`

### `claim_065`

- 原子 claim：U.S. Bureau of Labor Statistics: "In August, average hourly earnings for all employees on private nonfarm payrolls rose by 10
cents, or 0.3 percent, to $37.75."
- Scope：subject=`average hourly earnings`；measure=`hourly earnings`；period=`August`；unit=`$`；certainty=`rose`
- Source context：`Establishment Survey Data` / `August average hourly earnings` / `registered exact evidence target`
- Exact evidence：`In August, average hourly earnings for all employees on private nonfarm payrolls rose by 10
cents, or 0.3 percent, to $37.75.`

### `claim_066`

- 原子 claim：U.S. Bureau of Labor Statistics: "The average workweek for all employees on private nonfarm payrolls edged up by 0.1 hour to
34.4 hours in August."
- Scope：subject=`average workweek`；measure=`workweek`；period=`August`；unit=`hours`；certainty=`edged up`
- Source context：`Establishment Survey Data` / `August average workweek` / `registered exact evidence target`
- Exact evidence：`The average workweek for all employees on private nonfarm payrolls edged up by 0.1 hour to
34.4 hours in August.`

### `claim_067`

- 原子 claim：U.S. Bureau of Labor Statistics: "The change in total nonfarm payroll employment for June was revised up by 11,000, from
+20,000 to +31,000"
- Scope：subject=`June`；measure=`change`；period=`June`；unit=`None`；certainty=`revised up`
- Source context：`Establishment Survey Data` / `June nonfarm payroll estimate revision in the August release` / `registered exact evidence target`
- Exact evidence：`The change in total nonfarm payroll employment for June was revised up by 11,000, from
+20,000 to +31,000`

### `claim_068`

- 原子 claim：U.S. Bureau of Labor Statistics: "the change for July was revised up by 44,000, from -23,000 to +21,000."
- Scope：subject=`July`；measure=`change`；period=`July`；unit=`None`；certainty=`revised up`
- Source context：`Establishment Survey Data` / `July nonfarm payroll estimate revision in the August release` / `registered exact evidence target`
- Exact evidence：`the change for July was revised up by 44,000, from -23,000 to +21,000.`

### `claim_069`

- 原子 claim：U.S. Bureau of Labor Statistics: "Employment in food services and drinking places increased by 59,000 in August"
- Scope：subject=`food services and drinking places`；measure=`employment`；period=`August`；unit=`None`；certainty=`increased`
- Source context：`Establishment Survey Data` / `August employment change in food services and drinking places` / `registered exact evidence target`
- Exact evidence：`Employment in food services and drinking places increased by 59,000 in August`

### `claim_070`

- 原子 claim：U.S. Bureau of Labor Statistics: "Local government education added 42,000 jobs in August"
- Scope：subject=`local government education`；measure=`jobs`；period=`August`；unit=`None`；certainty=`added`
- Source context：`Establishment Survey Data` / `August employment change in local government education` / `registered exact evidence target`
- Exact evidence：`Local government education added 42,000 jobs in August`

### `claim_071`

- 原子 claim：U.S. Bureau of Labor Statistics: "Information employment declined by 23,000 in August"
- Scope：subject=`information employment`；measure=`employment`；period=`August`；unit=`None`；certainty=`declined`
- Source context：`Establishment Survey Data` / `August employment change in the information industry` / `registered exact evidence target`
- Exact evidence：`Information employment declined by 23,000 in August`



## 审核边界

- `餐饮业` 未获批，避免扩张 `food services and drinking places` 的范围。
- `非农薪资就业总人数` 未获批。
- 所有批准映射都受 case、run、当前 Facts SHA 与具体 claim scope 限制；未知中文术语继续 fail closed。
