# BLS 2026 年 8 月就业报告 Storyboard 人工审查包

**当前候选：待人工审核。** 原始 Storyboard 的人工决定为 `CHANGES_REQUIRED`；下方展示经过通用恢复 API 修改、重新验证并登记的新候选。自动验证通过不等于人工批准，也不授权生成视觉素材、Timeline 或 MP4。

## 1. 原始决定与恢复候选

| 项目 | 记录 |
|---|---|
| Case / Run | `bls-aug-2026-employment` / `2026-09-27-001-bls-august-2026-employment-situation` |
| 原 Storyboard | `storyboard.json`；schema `5.0`；SHA-256 `a649b81656193ffbac7898361d9c6b7227b9bd2411cf1208756c1b1e6b85e9e6` |
| 原人工决定 | `CHANGES_REQUIRED`；原因 `VISUAL_DIFFERENTIATION_AND_HIERARCHY`；reviewer `motty63-ctrl`；`2026-09-29T15:42:57+08:00` |
| 决定范围 | 视觉区分度与层级需要改进；不是对 scene 数量、顺序、时间、segment 所有权、事实绑定、Script、音频、alignment 或字幕的否定 |
| 恢复路径 | 之前没有可复用的通用 Human Storyboard Recovery owner；现已添加通用、run-bound 的恢复 API 和依赖注册 |
| 人工编辑记录 | `runs/2026-09-27-001-bls-august-2026-employment-situation/human_storyboard_edit.json`；文件/注册 SHA-256 `134150cab8ef623d28fc41427f1566755b5caf157f87cf39a6a67ee2906f8313`；状态 `pending_human_review` |
| 编辑来源 | reviewer `motty63-ctrl`；提交时间 `2026-09-29T15:42:57+08:00`；理由：改善视觉区分度和层级，同时保留已审 Script、事实、claims、scene 结构、音频 alignment 与 timing |
| 恢复候选 | `runs/2026-09-27-001-bls-august-2026-employment-situation/human_storyboard_candidate.json`；canonical candidate SHA-256 `9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`；文件/注册 SHA-256 `920299f4a2e483c5a6aeaeb2afaaa884cdd1a3c04b9c0b1c8d5bd3ca2cc5e7f3` |
| 重新验证 | 通用 Storyboard 安全验证与质量门禁通过；新候选仍等待第二次独立人工审查 |

恢复候选不是视觉制作批准。原始 `storyboard.json` 和 `storyboard_review.json` 保留为历史证据；候选拥有单独身份。`visual_plan.md` 已由正式 owner 从已登记候选重渲染。候选继续绑定原 Script、已批准音频、Human Audio Review、alignment、字幕、angle selection、Facts 与 run identity。

## 2. 依赖与时间来源

| 输入 | 当前绑定 |
|---|---|
| Angle selection | `angle_001`；SHA-256 `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77` |
| Script | SHA-256 `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` |
| Candidate 2 audio | SHA-256 `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183`；时长 `58,679 ms` |
| Human Audio Review | SHA-256 `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f` |
| Alignment | SHA-256 `66744f918fe01dd2e726858ee132eca81701f56f55a404124deb85068d641306` |
| Subtitle track | SHA-256 `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46`；12 cues |
| Facts | SHA-256 `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882` |

Timing basis 是 `alignment_derived`，scene range source 为 `alignment-derived`，方法是 `proportional_by_normalized_char_count`，质量为 `estimated`。它是按规范 narration segment 的归一化字符长度估算的句级 timing；不是声学对齐、词级精度或逐帧字幕时间。

Storyboard 保持 9 个 scene、原有顺序和 `0–58,679 ms` 时间范围。12 个 narration segment 仍按顺序、连续分组，各归属一个 scene，恰好覆盖一次。字幕仍使用 canonical Script 显示文本；视觉主层级可提炼信息，但不替换或缩写字幕内容。

## 3. 恢复后的完整 9-scene 计划

下表的 narration/display 文本来自已批准 Script 与当前字幕轨；视觉描述对应恢复候选。scene 仍是 Storyboard 计划，不表示画面资产已经制作。

| Scene / 时间 | Narration segments 与字幕 | 视觉层级 / 内容 | 支持 claims | 转场与审查注意 |
|---|---|---|---|---|
| `scene_001` · `0–3,848 ms` · 3.848s | `sentence_001` — “一份就业报告，别只盯着新增就业一个数字。” | 主标题“别只盯一个数字”；周围依次/环绕展开六个轻量类别：非农就业、失业率、工资、工时、修订、行业。无数值，表达从单一 headline 到多维报告的展开。 | 无；纯 framing hook。 | 开场展开至双指标。不能提前暗示报告结论或制造耸动判断。 |
| `scene_002` · `3,848–11,543 ms` · 7.695s | `sentence_002` — “美国劳工统计局报告，8月非农就业总人数增加16.2万。”；`sentence_003` — “失业率持平在4.1%。” | 两个独立并列卡片：左为“非农就业 / +16.2万”，右为“失业率 / 4.1% / 持平”。从本 scene 起显示轻量页脚 `Source: U.S. Bureau of Labor Statistics`。 | `claim_063`, `claim_064`；前者为 Establishment Survey，后者为 Household Survey。 | 两项是不同指标和调查体系；布局不得让人误以为同一统计序列。页脚不能压过数值。 |
| `scene_003` · `11,543–18,469 ms` · 6.926s | `sentence_004` — “私营非农部门平均时薪上涨10美分，涨幅0.3%，达到37.75美元。” | 工资数据卡：最大字号 `37.75美元`；次级 `+10美分`、`+0.3%`；标签“平均时薪”，范围“私营非农部门”。轻量 BLS 页脚。 | `claim_065`；Establishment Survey Data。 | 不以整句字幕充当主视觉；不可扩大为所有劳动者工资。 |
| `scene_004` · `18,469–24,434 ms` · 5.965s | `sentence_005` — “私营非农部门平均每周工时小幅上升0.1小时，至34.4小时。” | 与 scene 003 同字体/配色的指标家族，但使用静态钟面或时间刻度构图；最大值 `34.4小时`，次级 `+0.1小时`，标签“平均每周工时”。轻量 BLS 页脚。 | `claim_066`；Establishment Survey Data。 | 与工资构成一对但不能做成重复卡片；工时与工资是不同指标。 |
| `scene_005` · `24,434–30,398 ms` · 5.964s | `sentence_006` — “6月非农就业变动被上修1.1万，从增加2万修正为增加3.1万。” | 6月 before → after 卡：此前 `+2万` → 修订后 `+3.1万`；独立标记“上修 `+1.1万`”。轻量 BLS 页脚。 | `claim_067`；Establishment Survey Data。 | 修订幅度与修订后估计必须视觉分开；`+1.1万` 不是该月新增就业值。 |
| `scene_006` · `30,398–35,977 ms` · 5.579s | `sentence_007` — “7月变动被上修4.4万，从减少2.3万修正为增加2.1万。” | 沿用修订卡家族：此前 `−2.3万` → 修订后 `+2.1万`；独立标记“上修 `+4.4万`”。保留正负号及负转正的方向。轻量 BLS 页脚。 | `claim_068`；Establishment Survey Data。 | `+4.4万` 是估计修订幅度，不是7月当月就业变化；不把符号变化解释为因果或趋势结论。 |
| `scene_007` · `35,977–45,596 ms` · 9.619s | `sentence_008` — “餐饮服务和饮酒场所就业增加5.9万。”；`sentence_009` — “地方政府教育部门就业岗位数增加4.2万。”；`sentence_010` — “信息业就业减少2.3万。” | 单张等权三行卡，标题“部分行业变化”：餐饮服务和饮酒场所 `+5.9万`；地方政府教育部门 `+4.2万`；信息业 `−2.3万`。可使用简单正负方向条；不做名次。轻量 BLS 页脚。 | `claim_069`, `claim_070`, `claim_071`；Establishment Survey Data。 | 明确是部分例子，不是“前三/最大/主要行业”或全量排名；不暗示这些行业解释总就业变化。 |
| `scene_008` · `45,596–53,484 ms` · 7.888s | `sentence_011a` — “美国劳工统计局这份报告里，既有8月当期的非农就业、失业率、平均时薪和平均每周工时，” | 结构回顾板：主标签“8月当期指标”，只列“非农就业、失业率、平均时薪、平均每周工时”，不重复数字。分组区分就业/工资/工时与失业率。轻量 BLS 页脚。 | `claim_063`–`claim_066`。 | 目的为分类而非重复数据；保持 Household 与 Establishment Survey 边界清楚。 |
| `scene_009` · `53,484–58,679 ms` · 5.195s | `sentence_011b` — “也有6月、7月修订和部分行业变化，这些信息需要分开看。” | 三层收尾：`8月当期指标` / `6月、7月修订` / `部分行业变化`；主收束文案“这些信息需要分开看”。不加新数值、不重复前面数字，保留轻量 BLS 页脚。 | `claim_067`–`claim_071` 仅作为所归纳类别的支撑。 | 干净收尾；不把分类建议扩成因果、预测或政策结论。 |

## 4. Segment 所有权核对

| 顺序 | Segment ID | 唯一归属 |
|---:|---|---|
| 1 | `sentence_001` | `scene_001` |
| 2–3 | `sentence_002`, `sentence_003` | `scene_002` |
| 4 | `sentence_004` | `scene_003` |
| 5 | `sentence_005` | `scene_004` |
| 6 | `sentence_006` | `scene_005` |
| 7 | `sentence_007` | `scene_006` |
| 8–10 | `sentence_008`, `sentence_009`, `sentence_010` | `scene_007` |
| 11 | `sentence_011a` | `scene_008` |
| 12 | `sentence_011b` | `scene_009` |

覆盖率为 **12/12；每段恰好一次；顺序及连续分组不变**。scene ID `scene_001`–`scene_009`、时间戳和 segment 所有权均与原 Storyboard 一致。

## 5. 自动安全检查摘要

- **数字显示：** 使用已批准事实的中文展示形式：`+16.2万`、`4.1%`、`37.75美元`、`+10美分`、`+0.3%`、`34.4小时`、`+0.1小时`、`+2万`、`+3.1万`、`+1.1万`、`−2.3万`、`+2.1万`、`+4.4万`、`+5.9万`、`+4.2万`。底层 Facts 未改。
- **修订语义：** June 的 `+2万 → +3.1万` 和独立 `上修 +1.1万`；July 的 `−2.3万 → +2.1万` 和独立 `上修 +4.4万`。候选没有把修订幅度写成当月就业变化。
- **Claim 与范围：** 事实数字继续绑定原有 eligible claim 和 sentence IDs；未新增事实、claim、预测或因果。行业内容仍限定为部分例子。
- **调查口径：** 失业率为 Household Survey；非农就业、工资、工时、修订和行业项目为 Establishment Survey。两个调查系统在 scene 002 与 recap 中保持区分。
- **来源归属：** 从 scene 002 起规划稳定、轻量的 `Source: U.S. Bureau of Labor Statistics` 页脚；开场不加页脚，以免干扰 hook。
- **字幕与视觉层级：** canonical Script 字幕完整保留；主视觉聚焦标签、数值与分类，不要求把整句字幕当成每场主标题。
- **安全门禁：** 同一通用恢复验证检查 scene/timing/segments 不可变、claim eligibility、数值与正负号、修订语义、行业范围和 Storyboard quality gate。恢复候选验证通过，但仍需人工审看可读性和视觉表达。
- **时间精度：** 仅为比例字符长度估算的句级 timing，质量 `estimated`；没有声学对齐或词级强制对齐证据。

## 6. 第二次人工审查清单

- [ ] Scene 001 从单一 headline 展开到多个报告维度是否清楚
- [ ] Scene 002 的双指标布局是否容易理解
- [ ] Scene 003 工资与 scene 004 工时是否同属一套视觉家族、又能清楚区分
- [ ] June 修订是否分清此前值、修订后值和修订幅度
- [ ] July 负转正是否明显且正负号清楚
- [ ] 行业场景是否明确写“部分行业变化”
- [ ] 行业场景是否避免暗示排名
- [ ] Scene 008 是否避免重复所有数值
- [ ] Scene 009 是否构成清楚的三类信息收尾
- [ ] 来源页脚是否持续出现且不抢主视觉
- [ ] 字幕层与主要视觉信息层级是否有所区分
- [ ] 全片视觉词汇是否连贯
- [ ] 是否有场景信息过密或文字过多
- [ ] 整体节奏是否仍适配既有时间范围

## 7. Gate

**HUMAN STORYBOARD REVIEW = PENDING**

本包供对恢复候选进行第二次人工审查。未得到单独明确批准前，不生成图像、图表、SVG、场景 PNG、下载素材或 motion graphics；不创建 Timeline，不渲染 MP4，也不把当前候选视作 `approved_for_visual_generation`。
