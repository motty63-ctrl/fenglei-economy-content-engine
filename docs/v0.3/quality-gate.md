# V0.3 Script Quality Gate

`script.json` is written only when every hard gate passes. `script.md` is then rendered from that valid JSON as narration-only text.

1. **Schema:** ordered structured sentences, permitted section/type enums, unique IDs, and a selected eligible angle.
2. **Fact eligibility:** every `verified_fact` has existing claim IDs whose facts are verified, downstream-allowed, and backed by eligible evidence.
3. **Undeclared facts:** numbers, dates, percentages, currencies, named-institution conclusions, policies, and definitive data verbs trigger fact validation even if labelled otherwise.
4. **Value and entity entailment:** factual values and named entities occur in the cited claim/evidence; no invented calculations, forecasts, or extrapolations. A rounding statement is allowed only when local `Decimal` comparison proves that eligible observations for the same metric/country/year differ solely by precision.
5. **Conflict:** conflicted claims cannot support determinate assertions. Dispute use is off by default and, when explicitly enabled later, must present the disagreement rather than choose a winner.
6. **Hook truthfulness:** the first section fits five seconds and its contrast is supported or phrased as a question/misunderstanding. False conflict, exaggeration, and missing qualifications fail.
7. **Duration:** `estimated_duration_seconds = effective_spoken_characters / configured_rate`. The default rate is 4.0 characters/second, valid configuration is 2.5–6.0, and the result must be 60–90 seconds. JSON metadata is excluded.
8. **Structure:** ordered hook → phenomenon → mechanism → core judgment; at least one explanation/mechanism sentence; the final section is one clear judgment sentence.
9. **Jargon:** no unexplained run of three domain terms in one sentence and no excessive configured jargon density. Necessary terms must be explained on first use.
10. **Orality:** reject production directions, written-report phrasing, parenthetical chains, list-table syntax, and sentences longer than 48 effective Chinese characters or containing more than three logical clauses.
11. **Originality:** apply the contiguous-overlap, 5-gram, distinctive-expression, case, metaphor, and structure rules from the specification.
12. **Traceability:** every `script.json` verified-fact sentence has at least one resolvable claim ID. `script.md` contains no claim IDs or internal annotations.

The lint result is deterministic and returns issue codes with sentence IDs, severity, and safe messages. Any error prevents the registry write. Warnings remain in stage diagnostics but do not silently change the draft.
