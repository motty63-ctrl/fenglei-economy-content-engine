# BLS Case 2 — Audio Review

**HUMAN AUDIO REVIEW = PENDING**

本文件记录本次获批 Script 的 TTS 产物和技术检查结果，供人工实际试听。技术 QA 通过不等于声音质量获批；请完成文末清单后再由正式 owner 记录决定。

## A. 审批链

- Case：`bls-aug-2026-employment`
- Run：`2026-09-27-001-bls-august-2026-employment-situation`
- 已选 angle：`angle_001`
- Script SHA-256：`450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305`
- Human Script Approval SHA-256：`8653415689546d56295f857722840de61f14d26515d836f077a1a13818e3c59f`
- Approval status：`approved_for_tts`；target language：`zh-CN`
- Provider / model / voice：`volcengine_tts` / `volcengine-v3-sse` / `zh_male_liufei_uranus_bigtts`
- Speaking rate / pitch / volume：`1.0` / `0.0` semitones / `0.0` dB
- Audio generation completed：`2026-09-29T10:37:55+08:00`
- Facts SHA-256：`f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882`

本次没有修改 Script、术语审批、Facts、Research 或 narration 文本，也没有创建新的 Script approval。

## B. 网络传输与请求结果

先前请求在本机 `urlopen` socket 阶段报 Windows `WinError 10013`，没有 HTTP response 或 provider request ID。DNS 解析成功；普通沙箱中的 TCP 连接被拒绝。经正常的受支持网络权限提升后，对同一 host 的 TCP/443 和 TLS 1.3 连接成功，随后通过现有 Volcengine adapter 完成了一次 production TTS 请求。未关闭防火墙、修改系统安全配置或使用代理。

- Adapter endpoint：`https://openspeech.bytedance.com/api/v3/tts/unidirectional`（报告 host `openspeech.bytedance.com:443`；不记录凭证或认证头）
- Production request：一次合并旁白请求成功；12 个规范段落依序组成当前 canonical narration 输入。没有主观重试或替代 voice。
- Provider request ID：当前 adapter 输出的 metadata 未提供/持久化该 ID，故不可报告。

## C. 音频文件

- Canonical path：`runs/2026-09-27-001-bls-august-2026-employment-situation/audio/narration.wav`
- 本地完整路径：`D:\Projects\fanglei-economy-content-engine\runs\2026-09-27-001-bls-august-2026-employment-situation\audio\narration.wav`
- SHA-256：`54b112a49a3e9d8dba484067ee2deaffa3aa043cb20ea0c9e58546a0b0a9af6a`
- 文件大小：2,949,538 bytes
- Format / codec：WAV / PCM signed 16-bit little-endian
- Sample rate / channels：24,000 Hz / 1（mono）
- Duration：61.448 s（由 1,474,747 个采样帧计算为 61.447792 s；metadata 按毫秒记录）
- Script estimate：65.0 s
- Difference（audio − estimate）：-3.552 s；没有自动变速或拉伸。

## D. 规范旁白段落覆盖

这是一个合并 WAV，不存在每个段落单独的音频文件、时间偏移或独立 duration；表格列出发送给 TTS 的 Script 原文及 canonical narration 规范化文本。顺序和文本映射与当前 `script.json` / `narration.json` 一致，但文件本身未做 ASR/forced-alignment 证明。

| Segment | Script 原文 | 发送给 TTS 的 narration 文本 | 音频覆盖与 timing | 状态 |
|---|---|---|---|---|
| `sentence_001` | 一份就业报告，别只盯着新增就业一个数字。 | 一份就业报告，别只盯着新增就业一个数字。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_002` | 美国劳工统计局报告，8月非农就业总人数增加16.2万。 | 美国劳工统计局报告，八月非农就业总人数增加一六点二万。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_003` | 失业率持平在4.1%。 | 失业率持平在百分之四点一。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_004` | 私营非农部门平均时薪上涨10美分，涨幅0.3%，达到37.75美元。 | 私营非农部门平均时薪上涨一〇美分，涨幅百分之〇点三，达到三七点七五美元。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_005` | 私营非农部门平均每周工时小幅上升0.1小时，至34.4小时。 | 私营非农部门平均每周工时小幅上升〇点一小时，至三四点四小时。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_006` | 6月非农就业变动被上修1.1万，从增加2万修正为增加3.1万。 | 六月非农就业变动被上修一点一万，从增加二万修正为增加三点一万。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_007` | 7月变动被上修4.4万，从减少2.3万修正为增加2.1万。 | 七月变动被上修四点四万，从减少二点三万修正为增加二点一万。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_008` | 餐饮服务和饮酒场所就业增加5.9万。 | 餐饮服务和饮酒场所就业增加五点九万。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_009` | 地方政府教育部门就业岗位数增加4.2万。 | 地方政府教育部门就业岗位数增加四点二万。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_010` | 信息业就业减少2.3万。 | 信息业就业减少二点三万。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_011a` | 美国劳工统计局这份报告里，既有8月当期的非农就业、失业率、平均时薪和平均每周工时， | 美国劳工统计局这份报告里，既有八月当期的非农就业、失业率、平均时薪和平均每周工时， | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |
| `sentence_011b` | 也有6月、7月修订和部分行业变化，这些信息需要分开看。 | 也有六月、七月修订和部分行业变化，这些信息需要分开看。 | 合并 WAV；该段按输入顺序提交，无独立时间戳/时长 | 已包含；发音待人工听审 |

## E. 技术 QA

| 检查项 | 结果 | 依据 / 限制 |
|---|---|---|
| Decode / file integrity | **OK** | Python WAV decoder 完整读取文件；非空，1,474,747 frames。 |
| Format / sample metadata | **OK** | WAV、PCM16、mono、24 kHz，与当前配置一致。 |
| Full-text coverage | **CAUTION** | 12 段规范文本均在单次合并请求中提交；没有 ASR 比对，无法仅靠元数据证明合成音逐字完整。 |
| Input ordering | **OK** | 请求输入按 `narration.json` 的 12 段顺序组合；声学播放顺序仍应试听确认。 |
| Missing audio file | **OK** | canonical `audio/narration.wav` 存在且完整解码。 |
| Truncation / beginning and ending | **CAUTION** | 容器与帧数据完整；没有逐字转写或声学截断检测，尤其请试听开头和结尾。 |
| Long silence | **CAUTION** | 现有质量工具报告 voiced ratio 80.6%（voiced 49.520 s）；它不检测最长静音区间，请试听停顿。 |
| Clipping | **OK** | peak -6.77 dBFS，现有质量 gate 通过；这不替代主观听感检查。 |
| Duration | **CAUTION** | 61.448 s，比 Script 的 65.0 s 估计短 3.552 s；未自动 time-stretch。 |
| Artifact registry | **OK** | audio WAV、metadata、quality 与当前 Script/narration dependency hashes 注册为 valid/current。 |

现有 QA 的 `production_eligible=true`、`passed=true`、`gate_reasons=[]`。没有 `audio/review.json`；人工审听仍未完成。

## F. 人工试听清单

请用播放器实际聆听：`D:\Projects\fanglei-economy-content-engine\runs\2026-09-27-001-bls-august-2026-employment-situation\audio\narration.wav`。逐项确认并记录任何时间点或问题：

1. 整体音色是否自然、易懂。
2. 语速是否适合短视频，尤其密集数据段。
3. 开场 hook 是否清楚，开头有无截断。
4. “16.2万”是否按原意读出（narration normalization 的拼读需要听确认）。
5. “4.1%”是否读作百分之四点一。
6. “37.75美元”是否读数准确且单位完整。
7. June revision 句：上修 1.1 万、增加 2 万、修订为增加 3.1 万，方向和数值是否清楚。
8. July revision 句：上修 4.4 万、从减少 2.3 万修订为增加 2.1 万，方向和数值是否清楚。
9. 行业数值 5.9 万、4.2 万、2.3 万是否清楚。
10. 行业名称及英文缩写/专名的发音是否自然。
11. 密集数字前后停顿是否足够。
12. 最后较长的收束句节奏是否自然，句尾是否完整。
13. 是否存在机械、含混、吞字、错读或容易误解的发音。

另请留意规范化文本中的高风险读法：`16.2万`、`4.1%`、`10美分`、`0.3%`、`37.75美元`、`0.1小时`、`34.4小时`、June/July revision 数字和行业数值。此处只提示核听，不代表已判定读音正确。

## G. 人工决定

**HUMAN AUDIO REVIEW = PENDING**

本报告不批准音频。完成试听后，由人工明确选择批准或要求修订；任何 Script 修改都必须重新经过对应的 Script review/approval 与 TTS 流程。

## 阶段边界

本阶段没有运行 alignment、subtitle timing、Storyboard、visual planning、Timeline 或 MP4 renderer；没有生成视频，也没有音频人工批准 artifact。
