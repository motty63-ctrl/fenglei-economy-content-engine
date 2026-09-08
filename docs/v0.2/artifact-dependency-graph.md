# Artifact Dependency Graph

```text
source.md
  └─ questions.json
       ├─ search_results.json
       │    └─ source_documents/index.json + source_documents/*.md
       │          └─ sources.json
       └────────────────────────────┐
                                    ├─ facts.json
sources.json ───────────────────────┘
  └─────────────────────────────────┐
facts.json ─────────────────────────┼─ research.md
questions.json ─────────────────────┘
```

`source_documents/index.json` 的 hash 代表整组原始文档；单个正文路径和元数据在 index 内登记。
