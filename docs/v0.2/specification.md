# V0.2 多源研究与事实核查规范

## 范围

V0.2 将 `questions.json` 转换为可追溯的 `search_results.json`、原始网页正文、`sources.json`、`facts.json` 和最终 `research.md`。Tavily 只发现 URL；snippet 永远不是事实证据。系统不包含视频、Web UI、发布或 V0.3 功能。

## Artifact 所有权

| Artifact | Owner | Dependencies |
| --- | --- | --- |
| `source.md` | `ingest` | - |
| `questions.json` | `analyze` | `source.md` |
| `search_results.json` | `search` | `questions.json` |
| `source_documents/index.json` | `source_fetch` | `search_results.json` |
| `sources.json` | `source_selection` | search results, source document index |
| `facts.json` | `factcheck` | questions, selected sources, source documents |
| `research.md` | `research_synthesis` | questions, sources, facts |

只有 owner 可写。每个状态保存 owner、status、content hash、created/updated 时间和依赖 hash。上游 hash 变化时，下游传递标为 `stale`；stale 不可读取。`--force-stage` 只允许 owner 重建自己的 artifact，不能绕过无效上游。

## 证据规则

高风险经济事实（经济数据、政策、利率、GDP、通胀、就业、汇率）只有在至少两个可确认独立、且至少一个为原始/权威来源的证据支持时标记 `verified`。冲突标记 `conflicted`，证据不足标记 `unverified`。任何进入报告的重要事实均显示 claim ID 和 source ID，并可从 evidence 的 locator 回到原网页。

## 失败语义

每阶段先写 `running`，成功原子写 artifact 后标 `succeeded`；异常标 `failed` 并保留错误。临时或失败内容不成为有效 artifact。再次执行时复用所有 valid 上游，从失败/过期节点继续。
