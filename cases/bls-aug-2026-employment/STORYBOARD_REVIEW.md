# BLS 2026 年 8 月就业报告 Storyboard 人工审查包

**审查状态：待人工审核。** 本文审查的是已生成的 Storyboard 5.0 与其 Markdown visual plan；Storyboard 自动质量门禁通过不等于人工批准，也不授权视觉资产生成、Timeline 或 MP4。

## A. 依赖链与身份

| 项目 | 当前绑定值 |
|---|---|
| Case / Run | `bls-aug-2026-employment` / `2026-09-27-001-bls-august-2026-employment-situation` |
| 人工选定角度 | `angle_001`；selection SHA-256 `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77` |
| Script | `script_001`；SHA-256 `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` |
| Human Script Approval | `motty63-ctrl`，`approved_for_tts`，`2026-09-29T10:27:36+08:00`；记录 SHA-256 `8653415689546d56295f857722840de61f14d26515d836f077a1a13818e3c59f` |
| Candidate 2 Audio | SHA-256 `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183`；时长 `58,679 ms` |
| Human Audio Review | `motty63-ctrl`，approved，`2026-09-29T12:45:14+08:00`；SHA-256 `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f` |
| Alignment | SHA-256 `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306`；方法 `proportional_by_normalized_char_count`；质量 `estimated` |
| Subtitle track | SHA-256 `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46`；12 cues |
| Storyboard | schema `5.0`；SHA-256 `a649b81656193ffbac7898361d9c6b7227b9bd2411cf1208756c1b1e6b85e9e6`；9 scenes |
| Storyboard planner | `DeterministicVisualPlanningProvider`；provider metadata `deterministic / visual-rules-v1 / visual-beats-v1`；本阶段外部调用 `0` |

本 Storyboard 仅关联已核验的 BLS 2026 年 8 月《Employment Situation》`src_001`（source role：`target-current-employment-estimates-and-industry-changes-2026-08`）。其精确 URL 为 <https://www.bls.gov/news.release/empsit.htm>。失业率 claim 绑定 Household Survey Data；非农就业、工资、工时、修订和行业 claim 绑定 Establishment Survey Data。批准包中的 July archive `src_002` 未被这些当前 Storyboard claim 引用；June / July 修订值是 August release 明确报告的修订结果，不代表本 Storyboard 已做跨 release 重算。

## B. Timing provenance

- scene ranges 来自当前 registered alignment artifact，并由 canonical narration segment IDs 汇总到各 scene；renderer 直接读取 Storyboard 中的 `start_ms`、`end_ms` 和 duration，不从 Script 重新计算。
- Timing basis：`alignment_derived`；scene range source：`alignment-derived`。
- Alignment method：`proportional_by_normalized_char_count`；quality：`estimated`。
- 音频绑定存在，时长 `58,679 ms`。全局 scene range 为 `0–58,679 ms`。
- 这些时间适合 Storyboard 节奏规划；它们**未证明为声学级或逐词精确对齐**，也**未获批为最终逐帧字幕时间**。
- 字幕采用与 canonical Script 一致的句级显示文本。不能把这条 alignment 描述成 WhisperX word-level forced alignment。

## C. 完整 9-scene Storyboard

表中 narration 与 display/subtitle 均取自当前 Script、Storyboard 和 subtitle track。每个 scene 的计划类型均为 `program_animation / single_scene`；当前对象是绑定句子与 claim 的文字对象，不代表已制作最终视觉资产。

| Scene / 时间 | 规范 narration segment IDs | Narration / display-subtitle text | 视觉目标 / 类型 / 画面主文字与数值 | Supporting claims / 来源归属 | 转场 / 风险与注意 |
|---|---|---|---|---|---|
| `scene_001`<br>`0–3,848 ms`<br>`3.848 s` | `sentence_001` | Narration：“一份就业报告，别只盯着新增就业一个数字。”<br>Display：“一份就业报告，别只盯着新增就业一个数字。” | 用开场问题提醒观众不要只看 headline payroll。<br>`program_animation / single_scene`<br>主文字：上述原句；无数值。 | 无事实 claim；这是 framing hook。 | `draw_or_reveal → semantic_morph`<br>注意不要提前暗示报告结论。 |
| `scene_002`<br>`3,848–11,543 ms`<br>`7.695 s` | `sentence_002`, `sentence_003` | Narration：“美国劳工统计局报告，8月非农就业总人数增加16.2万。”<br>Display 同 narration。<br><br>Narration：“失业率持平在4.1%。”<br>Display 同 narration。 | 并列呈现 August payroll 与 unemployment，但在视觉上区分调查口径。<br>`program_animation / single_scene`<br>主文字：两句原文；`+162,000`、`4.1%`。 | `claim_063`, `claim_064`；`src_001`。Payroll 来自 Establishment Survey；失业率来自 Household Survey。 | `continue_canvas → semantic_morph`<br>**重点：**不可画成同一调查序列或暗示两指标统计口径相同。BLS attribution 在第一句明示；第二句依同一发布语境。 |
| `scene_003`<br>`11,543–18,469 ms`<br>`6.926 s` | `sentence_004` | Narration：“私营非农部门平均时薪上涨10美分，涨幅0.3%，达到37.75美元。”<br>Display 同 narration。 | 单独突出私营非农部门平均时薪的当月变动和水平。<br>`program_animation / single_scene`<br>主文字：原句；`+$0.10`、`+0.3%`、`$37.75`。 | `claim_065`；`src_001`，Establishment Survey Data。 | `continue_canvas → semantic_morph`<br>保留“私营非农部门”和 August 范围；不要扩成所有劳动者工资。 |
| `scene_004`<br>`18,469–24,434 ms`<br>`5.965 s` | `sentence_005` | Narration：“私营非农部门平均每周工时小幅上升0.1小时，至34.4小时。”<br>Display 同 narration。 | 与工资分开呈现每周工时指标。<br>`program_animation / single_scene`<br>主文字：原句；`+0.1 小时`、`34.4 小时`。 | `claim_066`；`src_001`，Establishment Survey Data。 | `continue_canvas → semantic_morph`<br>避免把工时变化与工资变化合并成同一度量。 |
| `scene_005`<br>`24,434–30,398 ms`<br>`5.964 s` | `sentence_006` | Narration：“6月非农就业变动被上修1.1万，从增加2万修正为增加3.1万。”<br>Display 同 narration。 | 展示 June 初值到修订值的方向与幅度。<br>`program_animation / single_scene`<br>主文字：原句；`+20,000 → +31,000`；revision `+11,000`。 | `claim_067`；`src_001`，Establishment Survey Data。 | `continue_canvas → semantic_morph`<br>**重点：**`11,000` 是修订幅度，不是 June 当月新增就业总量；`+31,000` 是修订后的 June estimate。 |
| `scene_006`<br>`30,398–35,977 ms`<br>`5.579 s` | `sentence_007` | Narration：“7月变动被上修4.4万，从减少2.3万修正为增加2.1万。”<br>Display 同 narration。 | 展示 July 修订前后从负值转为正值。<br>`program_animation / single_scene`<br>主文字：原句；`−23,000 → +21,000`；revision `+44,000`。 | `claim_068`；`src_001`，Establishment Survey Data。 | `continue_canvas → semantic_morph`<br>**重点：**`44,000` 是估计修订幅度，不是 July 当月新增就业；负转正须保留正负号。 |
| `scene_007`<br>`35,977–45,596 ms`<br>`9.619 s` | `sentence_008`, `sentence_009`, `sentence_010` | Narration：“餐饮服务和饮酒场所就业增加5.9万。”<br>Display 同 narration。<br><br>Narration：“地方政府教育部门就业岗位数增加4.2万。”<br>Display 同 narration。<br><br>Narration：“信息业就业减少2.3万。”<br>Display 同 narration。 | 以两个增长行业和一个下降行业展示有正有负的局部变化。<br>`program_animation / single_scene`<br>主文字：三句原文；`+59,000`、`+42,000`、`−23,000`。 | `claim_069`, `claim_070`, `claim_071`；`src_001`，Establishment Survey Data。 | `continue_canvas → semantic_morph`<br>**重点：**这只是选取行业例子，不是全行业排名或完整分解；不要暗示三个行业解释总就业变化。 |
| `scene_008`<br>`45,596–53,484 ms`<br>`7.888 s` | `sentence_011a` | Narration：“美国劳工统计局这份报告里，既有8月当期的非农就业、失业率、平均时薪和平均每周工时，”<br>Display 同 narration。 | 回顾 August 当期指标集合，帮助观众把 payroll、失业率、工资、工时分开看。<br>`program_animation / single_scene`<br>主文字：原句；只显示期间标签“8月”，不新增数据值。 | `claim_063`–`claim_066`；`src_001`。涉及 Establishment 与 Household 两类调查。 | `continue_canvas → semantic_morph`<br>**重点：**四项不是同一个调查口径；画面需维持清晰分组。 |
| `scene_009`<br>`53,484–58,679 ms`<br>`5.195 s` | `sentence_011b` | Narration：“也有6月、7月修订和部分行业变化，这些信息需要分开看。”<br>Display 同 narration。 | 以克制的收束句把修订与行业例子归为不同观察类别，不添加结论。<br>`program_animation / single_scene`<br>主文字：原句；“6月”“7月”为期间标签。 | `claim_067`–`claim_071`；`src_001`。 | `continue_canvas → hold`<br>注意保持“分开看”的整理建议，不扩写成原因、趋势预测或政策结论。 |

## D. Segment coverage

| Canonical order | Segment ID | Owning scene |
|---:|---|---|
| 1 | `sentence_001` | `scene_001` |
| 2 | `sentence_002` | `scene_002` |
| 3 | `sentence_003` | `scene_002` |
| 4 | `sentence_004` | `scene_003` |
| 5 | `sentence_005` | `scene_004` |
| 6 | `sentence_006` | `scene_005` |
| 7 | `sentence_007` | `scene_006` |
| 8 | `sentence_008` | `scene_007` |
| 9 | `sentence_009` | `scene_007` |
| 10 | `sentence_010` | `scene_007` |
| 11 | `sentence_011a` | `scene_008` |
| 12 | `sentence_011b` | `scene_009` |

覆盖为 **12/12；每段恰好一次；按 canonical 顺序；scene 分组连续**。Storyboard quality gate 为 passed，sentence coverage ratio 为 `1.0`。

## E. 内容覆盖

| 内容项 | 覆盖 | 依据与边界 |
|---|---|---|
| Hook | COVERED | `scene_001` 提醒不要只看新增就业一个数字。 |
| Payroll | COVERED | August total nonfarm payroll，`claim_063`。 |
| Unemployment | COVERED | August rate，`claim_064`；Household Survey。 |
| Earnings | COVERED | 平均时薪，`claim_065`。 |
| Workweek | COVERED | 平均每周工时，`claim_066`。 |
| June revision | COVERED | `claim_067`，旧值、修订值和修订幅度均被表达。 |
| July revision | COVERED | `claim_068`，保留由负转正、修订值和幅度。 |
| Positive industry examples | COVERED | 两个已核验增长例子，`claim_069`、`claim_070`；不代表完整行业列表。 |
| Negative industry example | COVERED | 一个已核验下降例子，`claim_071`；不代表完整行业列表。 |
| Closing | COVERED | `scene_009` 提醒将当期指标、历史修订和行业变化分开看。 |
| Overall industry landscape | PARTIAL | 当前只呈现两个增长行业和一个下降行业，不是完整排名或全量行业归因。 |

## F. Visual safety audit

| 检查项 | 结果 | 审查说明 |
|---|---|---|
| 数值正确性 | OK | 画面文字中的数值与所绑定 verified claims `claim_063`–`claim_071` 一致。 |
| Claim support | OK | 每个事实文字对象均绑定脚本 sentence ID 与相应 supporting claim IDs。 |
| June revision semantics | OK | `+20,000 → +31,000` 是 June estimate 的修订前后值；`+11,000` 是 revision amount，不是月度 payroll change。 |
| July revision semantics | OK | `−23,000 → +21,000` 是 July estimate 的修订前后值；`+44,000` 是 revision amount，不是月度 payroll change。 |
| Industry partial scope | CAUTION | 只呈现 selected examples；需避免把它们包装为完整行业排序或总变化的原因。 |
| Source attribution | CAUTION | 文本在 `sentence_002` 明示 BLS；其余事实句带 `bls-release` attribution context ID，但句面未重复机构名。最终视觉方案应检查是否有持续可见的 BLS / August release 来源标识。 |
| Unsupported causality | OK | 没有声称行业或某项指标导致总就业变化。 |
| Unsupported prediction | OK | 没有作未来就业或经济预测。 |
| Display vs spoken text | OK | Subtitle/display text 与 canonical Script 对齐；TTS 数字口语化仅在 narration 音频，不覆盖画面文字。 |
| Timing provenance | CAUTION | 来源与方法已准确标为 alignment-derived、proportional、estimated；并非词级声学对齐或最终逐帧字幕批准。 |

目前只审查文本 Storyboard 与 visual plan，没有视觉资产可供检查文字溢出、字号或真实画面层级。

## G. Human Storyboard Review checklist

- [ ] 9 个 scene 的数量和顺序是否合适
- [ ] 整体 pacing 是否自然
- [ ] 每个画面的信息密度是否合适
- [ ] 数字在手机屏幕上是否容易辨认
- [ ] Payroll 与 unemployment 是否清楚区分
- [ ] Earnings 与 workweek 是否清楚区分
- [ ] June revision 的前值、修订值与修订幅度是否清楚
- [ ] July revision 的正负变化与修订幅度是否清楚
- [ ] 行业 scene 是否明确为部分例子
- [ ] BLS 来源归属是否持续、清楚可见
- [ ] 连续 `single_scene` 文字画面是否显得重复
- [ ] scene transition 是否自然
- [ ] closing 是否有力且克制
- [ ] 全片视觉逻辑是否连贯

## H. Gate

**HUMAN STORYBOARD REVIEW = PENDING**

Storyboard 自动质量门禁仍为 passed；此文档不构成新的 Storyboard approval。未完成独立人工审核前，不开始 visual asset production、Timeline 或 MP4 rendering。
