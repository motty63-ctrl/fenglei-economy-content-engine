# Final Video Review — 已完成人工终审

**HUMAN FINAL VIDEO REVIEW = APPROVED · V0.2 ACCEPTANCE = ACCEPTED**

Reviewer `motty63-ctrl` 于 `2026-10-02T10:34:32.323781Z` 通过 canonical owner 批准本视频；[正式记录审计副本](FINAL_VIDEO_APPROVAL.json)，SHA `3605deaa54caa24d5048fe5e8dce0b96c853b52741489661253beeb9b23fa910`。审批绑定 immutable Candidate、当前 passed QA Attempt 2 与 FinalRenderRequest 的完整 current 依赖链。

媒体、Candidate、原 QA Attempt 1/2 与 Preview 都未修改。独立工作流审计见 [V0_2_ACCEPTANCE_REVIEW.md](V0_2_ACCEPTANCE_REVIEW.md)，非发布授权。

---

以下是人工批准前的 **historical review packet**。其中 PENDING、请求人工检查和 next action 是此前阶段快照，已由上述独立批准及验收记录 supersede；保留所有历史证据与 caution。

# BLS Final Video — Human Review Packet

**V0.2_PHASE_3C6B3_WAITING_FOR_FINAL_VIDEO_REVIEW**

HUMAN FINAL VIDEO REVIEW = PENDING
V0.2 ACCEPTANCE = PENDING

本文件是技术验收与人工终审材料，不是批准记录。本阶段没有重渲染、修改 Final Media / Candidate、发布或上传。

## 本地视频与不可变身份

[打开现有 Final Candidate 视频](../../runs/2026-09-27-001-bls-august-2026-employment-situation/final.mp4)

- Run：`2026-09-27-001-bls-august-2026-employment-situation`
- Case：`bls-aug-2026-employment`
- Media SHA-256：`5167703eeb0dd1855c30c2012ad0f1a44dbbed6617f27231b34332f93c723cdd`
- Candidate：`final_video_candidate.json` · `final-video-candidate/1.0`
- Candidate SHA（QA 前 / 后相同）：`52f901cabf73ccee056a98d4a062c4412c2e82703e553ec01f66a81c4a386a93`
- 208 个既有 run 文件保持原 hash；仅 `run.json` 更新登记，新增独立 QA Attempt 2。

## 批准链与 currentness

FinalRenderRequest owner 与 registry 已重新验证所有依赖。以下相对路径均位于本 run。

| Artifact | SHA-256 |
|---|---|
| `human_preview_review_candidate_3.json` | `9a746fe7dbfe6ff872dfaf1f11a98eabab3f80f7a0387fb9c18f8e8c2a954c55` |
| `review-preview-candidate-3.mp4` | `0421363e620e56429e8b14b3dead33b5fbdbf99f1b0eda1ecece917b9738f4fe` |
| `timeline_candidate_2.json` | `3e60ff14724751cef59d252e013c76950db37cacc30f99f515aa4e1db9da6642` |
| `visual_assets_candidate_3` | `5786ac2a2fd1627159969e3fba10a92e4d51822ba611d601c4a2c17e45806355` |
| `audio/narration.wav` | `36c09d917fed2c58ae2231b4ff4d5e9b8660320c84f8d85074f651830f1c0183` |
| `human_storyboard_candidate.json` | `920299f4a2e483c5a6aeaeb2afaaa884cdd1a3c04b9c0b1c8d5bd3ca2cc5e7f3` |
| `script.json` | `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` |
| `subtitle_track.json` | `58107e68f9f726e2bb0d3812a0db2b0f58240a07c656fc1c015aecfcd652ed46` |
| `preview_subtitle_track_candidate_2.json` | `bc872a3255594871210f0edf28d0842c0128a2a9d2cb0977f667153d1a0cca20` |
| `renderer_project_candidate_3` | `b073d8cef8d50c4bb1b7f443adfabcf2b3773579912c9b20ddafc5d846572d1d` |
| `render_manifest_candidate_3.json` | `52f058f0ccddeba34b58257c0a999c95e5cb75e9f2066d51dea941bc4a22acee` |
| `human_script_approval.json` | `8653415689546d56295f857722840de61f14d26515d836f077a1a13818e3c59f` |
| `audio/review.json` | `32b319d02b77a1953feff58ff23084e81c18667575196e1ad5b4e023252bff1f` |
| `human_storyboard_approval.json` | `6da7aa4e6628023d97054104972b62759ff79dc8d4764ef5212333a8efd76f05` |
| `human_visual_asset_review_candidate_3.json` | `a92d5d010c2ae2389ca8cd8c85da3bb5614dfaae684326e2e3390505004c11b3` |
| `final_render_request.json` | `1f5ea05edaadfb96bad0285382ed06fed671f22846f3db52781f012732a40269` |

Storyboard canonical SHA：`9bea77de9cf78eb0398a57bf67d0e728a4ddda3cb2cdaf1ae16e6e1448aacded`。所有批准输入保持不变；没有新建任何 human approval。

## QA 尝试历史

| Attempt | Artifact | Owner / schema | Result | SHA-256 |
|---|---|---|---|---|
| 1 | `final_video_qa.json` | owner 1.0 / final-video-qa/1.0 | FAILED：`MP4_BOX_SIZE_INVALID` | `f59839e21966de3901121c71147b32b32669ac306f0652d5f0c4ac0100783a01` |
| 2（current） | `final_video_qa_attempt_2.json` | owner 1.1 / final-video-qa/1.1 | PASSED | `ab520249af764b3f8823bee8aea066e22b152309785e06379205ca4acb1746ce` |

Attempt 1 bytes 原样保留；Attempt 2 用 `previous_qa` 显式绑定它，并绑定同一 Media / Candidate / Request / Preview / Timeline。Candidate 中的旧 `technical_qa_artifact` anchor 保持不变；当前报告由 registry 的 attempt chain 解析，人工门禁绑定 Attempt 2 SHA。

- QA 执行时间：`2026-10-02T10:10:51.028329Z`
- QA implementation SHA：`58a1a517c91357e18f8c1f34bdb9d37d15bbb3e313a39368a3891c744a622953`
- 技术属性来自项目本地 ffprobe JSON；完整 playback 与画面/字幕区域比较来自 Chromium。
- Human Final Review entry：`ready_for_human_review`；没有记录终审决定。

## Final 与 Preview 3 技术对比

| 属性 | Final | Preview 3 |
|---|---|---|
| 分辨率 | 1080×1920 | 1080×1920 |
| FPS | 30.0 | 30.0 |
| 帧数 | 1761 | 1761 |
| 视频 codec | h264 | h264 |
| 音频 codec | aac | aac |
| 容器时长（s） | 58.71 | 58.7 |
| 视频时长（s） | 58.7 | 58.7 |
| 音频时长（s） | 58.688 | 58.679 |
| 音频采样率 | 48000 | 48000 |
| 声道 | 2 | 2 |

Final 文件大小：3,579,255 bytes。完整 Chromium playback：1761 decoded frames、0 dropped frames、无错误；此前同一 SHA 的独立 FFmpeg 完整视频/音频 decode 均通过。

39 个实际画面样本包含 9 个 scene interior、12 个 subtitle cues、16 个边界两侧、opening / ending。相似度为像素 RGB 平均差归一化指标，并非 SSIM；门槛保持 0.94。

| 验证项 | Result | 摘要 |
|---|---|---|
| `media_exists` | PASS | Registered candidate media is non-empty. |
| `full_media_decode` | PASS | Chromium decoded the complete final video playback. |
| `video_stream` | PASS | MP4 contains a video track. |
| `audio_stream` | PASS | MP4 contains an audio track exposed by the media decoder. |
| `video_dimensions` | PASS | Encoded dimensions match the approved render configuration. |
| `frame_rate` | PASS | Encoded sample timing matches the approved frame rate. |
| `frame_count` | PASS | Encoded frame count is within the approved render tolerance. |
| `video_codec` | PASS | Encoded video codec matches the approved profile. |
| `audio_codec` | PASS | Encoded audio codec matches the approved profile. |
| `audio_properties` | PASS | Audio sample rate and channel count are present. |
| `container_duration` | PASS | Container duration matches the approved render within frame tolerance. |
| `audio_duration` | PASS | Audio track duration matches the approved timeline within tolerance. |
| `scene_coverage` | PASS | Each Timeline scene has an actual interior frame matching the approved Preview. |
| `subtitle_coverage` | PASS | All exact Timeline subtitle texts are present in canonical and packaged metadata and their rendered regions match the approved Preview. |
| `subtitle_layout` | PASS | Subtitle geometry stays inside the canvas and respects the line limit. |
| `scene_boundary_regressions` | PASS | Frames on both sides of each scene boundary match the approved Preview. |
| `opening_completeness` | PASS | The opening frame matches the approved Preview and is not accidentally blank. |
| `ending_completeness` | PASS | The ending frame matches the approved Preview and is not accidentally blank. |
| `preview_final_comparison` | PASS | Final media preserves approved Preview geometry, timing, and sampled scene content. |
| `browser_media_load` | PASS | Browser loaded both media candidates. |

## 实际画面 / 边界检查与限制

- 9/9 scenes 匹配 Preview，interior 最低相似度 0.990037。
- 12/12 cues 的文本与 canonical / package 一致，字幕区域最低相似度 0.987082；canvas 边界和行数检查通过。
- 16/16 边界样本最低相似度 0.990081；包含 006→007（36.573s）、007→008（46.263s）、008→009（53.900s）两侧。
- Scene 003（17s 抽帧）保持工资内容，未出现 Hook 回归。
- Scene 008（52.8s 抽帧）长字幕完整；未见裁切或 Source: BLS footer 遮挡。
- 9 个实际 scene 抽帧均已检查：未见空白、明显文字溢出或已批准数字变更。Opening / ending matching checks 均通过。
- CAUTION：现有获批 composition 仍显示 `PREVIEW · NOT FINAL`、`HUMAN REVIEW REQUIRED` 标签。本轮按 immutable Request 保留，技术 QA 不等于公开发布许可。
- CAUTION：部分字幕在汉字词组中间换行；未见裁切，但移动端阅读体验、语音节奏与字幕同步仍需人工整段观看。
- 浏览器画面相似度和布局 checks 是技术门禁，不能代替人工逐句确认事实、读音、观感及所有瞬间的 clipping。
- 没有修改 Script、音频、字幕、Storyboard、Visual、Timeline、Preview 或事实/Research。

## 人工终审清单（尚未批准）

- [ ] 完整观看 58.710s 视频并听完音频。
- [ ] Hook、开场及结尾完整；没有截断。
- [ ] 非农就业与失业率的调查口径清楚。
- [ ] 工资、工时及数字/单位无错误。
- [ ] June / July revision 未被误写为当月新增就业。
- [ ] 行业内容没有新增排名或因果解释。
- [ ] Scene 003 无 Hook 回归；Scene 008 长字幕可读。
- [ ] 三个关键边界无旧 scene 残留、提前字幕或错误重置。
- [ ] 字幕同步、分行、字号和移动端可读性可接受。
- [ ] 没有 clipping、overflow、footer collision 或 source attribution 缺失。
- [ ] 音量、停顿和读音可接受。
- [ ] 明确决定如何处理当前 Preview / human-review 标签；本轮未删除。
- [ ] 确认该 immutable Candidate 是否可以批准；批准须绑定 Candidate 与 current QA 的完整 SHA。

## 验证与停止边界

- Focused：57 passed。
- Safe non-integration：1018 passed、3 skipped、0 failures / errors；3 skips 是未配置 HyperFrames renderer-level fixture。
- `git diff --check`：通过。
- 通用修复 commit：`da7b855ad2777983a5febdb33e1bad734e40d421`。
- `docs/` update：`DEFERRED_REPARSE_POINT_ENVIRONMENT`；未绕过限制。
- No rerender / publication / release / tag / external upload / push。

**HUMAN FINAL VIDEO REVIEW = PENDING**
**V0.2 ACCEPTANCE = PENDING**
