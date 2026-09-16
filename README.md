# fanglei-economy-content-engine

AI-powered economic explainer video workflow for Fanglei.

经济知识短视频生产系统的 CLI 优先 MVP。V0.1 第一阶段将本地文章或粘贴文本规范化，并生成以研究问题为中心的持久化研究底稿。

## 安装

需要 Python 3.11 或更高版本：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

macOS 或 Linux 请将解释器路径替换为 `.venv/bin/python`。

## 使用

读取 UTF-8 编码的 `.txt` 或 `.md`：

```bash
python -m fanglei ingest article.md
```

直接传入短文本或通过标准输入粘贴多行内容：

```bash
python -m fanglei ingest --text "文章正文"
python -m fanglei ingest --stdin
```

命令返回 run ID 后执行分析：

```bash
python -m fanglei analyze 2026-09-07-001-topic-slug
```

执行 Tavily URL 发现、原网页抓取、多源去重、事实核查与研究合成：

```bash
TAVILY_API_KEY=... python -m fanglei research 2026-09-07-001-topic-slug
```

可用 `--stop-after STAGE` 停在指定 owner stage，或用 `--force-stage STAGE` 显式重建该阶段并令下游 stale。`--provider mock` 用于无网络的确定性演示；生产默认仍为 Tavily。

V0.2.1 对官方来源获取进行加固：确定性 API 路由、带页码的有限额 PDF 抽取、动态 HTML 失败检测、证据准入、脚本事实门和统一密钥脱敏。真实官方源测试必须显式设置 `RUN_OFFICIAL_INTEGRATION=1`；Tavily 搜索摘要始终只用于 discovery。

默认复用输入指纹和输出哈希均有效的已有分析。显式重跑会先保存旧产物：

```bash
python -m fanglei analyze 2026-09-07-001-topic-slug --force
```

可通过全局选项改变运行目录：

```bash
python -m fanglei --runs-dir D:/fanglei-runs ingest article.md
```

已通过 V0.4 的脚本与 storyboard 可用确定性 provider 生成 V0.5 的旁白、真实音频时间轴和 Nikola renderer 工程：

```bash
python -m fanglei prepare-renderer RUN_ID \
  --narration-provider fake \
  --alignment-provider fake \
  --probe fake
```

`--stop-after` 可停在任一 V0.5 stage，`--force-stage` 只重跑指定 stage；有效上游 artifact 默认复用。fake provider 仅用于确定性工程验收，真实 TTS、alignment 与 Nikola dry-run 均为显式 opt-in integration。

## Artifact 产物

每个任务目录至少包含：

- `source.md`：规范化原文和输入元数据；
- `questions.json`：核心主题、候选事实、作者观点、待验证主张、研究问题和单一来源风险；
- `research.md`：仅由 `research_synthesis` 写入的多源研究报告；
- `run.json`：可恢复的阶段状态、执行次数和产物哈希。

## 当前限制

- 分析使用确定性的 mock provider，不调用真实模型；
- `analyze` 只生成问题；`research.md` 必须经过检索、原文抓取与事实核查后生成；
- V0.5 尚未接入默认真实 TTS，也不生成正式 MP4；
- Nikola 真实 dry-run 需要本机另行提供 HyperFrames、浏览器、FFmpeg/FFprobe 和字体环境；
- 暂不提供 Web UI、n8n 或自动发布；
- 中文标题在没有 ASCII 字符时使用通用 `topic` slug。
# V0.5.1 real voice checkpoint

Production voice synthesis uses a replaceable `NarrationProvider` adapter. Install the
optional Azure SDK with `python -m pip install -e ".[azure-speech]"`, then set
`AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` in your local environment; configure
the voice ID explicitly. Never commit credentials or paste them into CLI arguments.

`python -m fanglei --runs-dir runs generate-voice RUN_ID --provider azure --voice-id VOICE_ID --language zh-CN --speaking-rate 1.0 --pitch-semitones 0 --volume-gain-db 0 --force`

This command consumes the existing narration artifacts and stops after canonical
`audio/narration.wav`, `audio/metadata.json`, and `audio/quality.json`. It does not
perform alignment, timeline compilation, or rendering. Listen to the WAV and verify
voice, rate, pauses, and number reading before explicitly approving the current
audio SHA with `approve-voice`. Regeneration invalidates any earlier approval.

The legacy fake audio pipeline remains test-only; its silent WAV and deterministic
alignment are not production narration or real speech timing.

Volcengine Seed TTS is available through the same provider-neutral contract. Set
`VOLCENGINE_TTS_API_KEY`, `VOLCENGINE_TTS_SPEAKER`, and
`VOLCENGINE_TTS_RESOURCE_ID` in the local process environment. The adapter requests
raw PCM and wraps it locally as canonical 24 kHz, mono, 16-bit WAV; credentials are
never written to artifacts. A live one-sentence smoke test is opt-in only:

`$env:RUN_VOLCENGINE_TTS_INTEGRATION='1'; python -m pytest tests/integration/test_volcengine_speech_live.py -q`

Remove `RUN_VOLCENGINE_TTS_INTEGRATION` after the smoke test. Do not run the GDP
narration until the smoke output has passed the production audio-quality gate.
