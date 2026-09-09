# V0.3 Model and Provider Interface

## Boundary

```python
class ContentPlanningProvider(Protocol):
    name: str
    model: str | None
    angle_prompt_version: str
    script_prompt_version: str

    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult: ...
    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft: ...
```

`AngleGenerationInput` contains `run_id`, topic, research questions, `research_md`, a tuple of `ScriptReadyClaim`, forbidden claim summaries, and style constraints. Each `ScriptReadyClaim` contains its ID/text plus eligible source IDs, institutions, evidence text, exact observations, locators, and metric/country/year context needed for traceability and local rounding checks. `ScriptGenerationInput` contains the selected `AngleCandidate`, the same claim palette, research context, duration limits, and sentence taxonomy.

The provider never receives `source.md`. It returns validated Pydantic objects and never writes files. Provider scores are advisory: local policy recomputes evidence strength, controversy risk, total score, duration, claim eligibility, and quality status.

## Output contracts

`AngleProposalResult` contains 3–5 `AngleProposal` objects with title, hook, core question, core insight, supporting claim IDs, proposed audience/novelty/hook/visual/explainability scores, and risk notes.

`ScriptDraft` contains ordered `ScriptSentence` objects. Each sentence has `sentence_id`, `section`, `sentence_type`, `text`, and `claim_ids`. Speaking rate, character count, estimated duration, lint status, recommendation, and final selection are computed outside the provider. The provider cannot mark an artifact valid.

## Implementations

V0.3 includes a deterministic `MockContentPlanningProvider` for TDD and offline acceptance. A real model adapter implements the same protocol and uses structured output; vendor SDK calls, credentials, retries, and redaction remain outside policy and artifact code. No model vendor is hard-coded into the V0.3 domain layer.
