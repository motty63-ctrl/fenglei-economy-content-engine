# V0.3 Angle Scoring Policy

Each dimension is an integer from 0 to 5. `evidence_strength` and `controversy_risk` are computed locally; provider ratings for other dimensions are bounded and checked against deterministic rubrics.

| Dimension | Weight | Meaning |
|---|---:|---|
| `evidence_strength` | 25 | Script-ready claims, eligible evidence, independent institutions, and claim-chain coverage |
| `audience_relevance` | 20 | Clear consequence for work, income, prices, saving, housing, consumption, or public choices |
| `novelty` | 15 | Distinct from source framing and sibling candidates; useful counter-intuitive insight |
| `hook_strength` | 15 | Immediate curiosity without exaggeration, omitted qualifications, or fabricated conflict |
| `visual_potential` | 5 | Future potential for a simple comparison or causal diagram; no storyboard is generated |
| `explainability` | 20 | One core question and a mechanism that fits ordinary-language explanation in 60–90 seconds |
| `controversy_risk` | penalty | 0 means low risk; 5 means misleading or unsupported conflict |

```text
base_score = evidence_strength*5 + audience_relevance*4 + novelty*3
           + hook_strength*3 + visual_potential*1 + explainability*4
total_score = max(0, base_score - controversy_risk*6)
```

The base score is 0–100. An eligible candidate requires evidence strength ≥2, audience relevance ≥2, explainability ≥3, hook strength ≥2, controversy risk ≤2, at least one script-ready claim, and no hard-rejection reason.

Hard rejection applies to unknown or forbidden claims, fabricated conflict, unsupported institutional conclusions, source-copying, materially duplicated candidates, or an insight that cannot fit the target duration. Selection sorts by `total_score`, then evidence strength, audience relevance, explainability, novelty, and finally `angle_id` for deterministic ties.

Evidence scoring: 0 for no usable claim; 2 for one script-ready claim; 3 for two claims or one claim with strong cross-institution evidence; 4 for a phenomenon-to-mechanism chain backed by multiple independent institutions; 5 for a complete chain with diverse primary/international evidence. Claim quantity alone cannot produce a 4 or 5.

Controversy risk: 0 for no conflict framing; 1 for a clearly labelled rounding/definition nuance; 2 for a supported genuine disagreement described neutrally; 3–5 for selective, exaggerated, or fabricated conflict and therefore rejection.
