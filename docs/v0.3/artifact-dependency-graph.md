# V0.3 Artifact Dependency Graph

```text
source.md ──→ questions.json ──→ search_results.json ──→ source_documents/index.json
                                      │                         │
                                      └──────────→ sources.json ┘
                                                        │
questions.json ────────────────────────────────→ facts.json
sources.json ──────────────────────────────────→ facts.json
source_documents/index.json ───────────────────→ facts.json

questions.json ─┐
sources.json ───┼─→ research.md
facts.json ─────┘

facts.json ─────┐
research.md ────┼─→ angles.json (`angle_generation`)
questions.json ─┤
source.md ──────┘  post-generation originality input only

angles.json ────┐
facts.json ─────┴─→ angle.md (`angle_selection`)

angle.md ───────┐
facts.json ─────┤
research.md ────┼─→ script.json (`script_generation`) ─→ script.md (`script_render`)
source.md ──────┘  post-generation originality input only
```

Owner stages are exclusive. Direct dependencies record the hashes actually consumed by each stage. A changed hash marks every transitive descendant stale; stale artifacts cannot be read as valid input.
