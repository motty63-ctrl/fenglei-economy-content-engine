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

默认复用输入指纹和输出哈希均有效的已有分析。显式重跑会先保存旧产物：

```bash
python -m fanglei analyze 2026-09-07-001-topic-slug --force
```

可通过全局选项改变运行目录：

```bash
python -m fanglei --runs-dir D:/fanglei-runs ingest article.md
```

## Phase 1 产物

每个任务目录至少包含：

- `source.md`：规范化原文和输入元数据；
- `questions.json`：核心主题、候选事实、作者观点、待验证主张、研究问题和单一来源风险；
- `research.md`：按研究问题组织的研究底稿；
- `run.json`：可恢复的阶段状态、执行次数和产物哈希。

## 当前限制

- 分析使用确定性的 mock provider，不调用真实模型；
- `research.md` 是研究议程，不代表已经执行外部检索或事实核查；
- 暂不支持 URL 抓取、视频、Web UI、n8n、自动发布、TTS 或 FFmpeg；
- 中文标题在没有 ASCII 字符时使用通用 `topic` slug。
