# Runbook

Commands below are PowerShell-compatible and operate on the selected `runs/` directory. Replace `RUN_ID` with the exact existing directory name. Check `run.json` and artifact status before retrying any stage.

## Create and advance a native run

Create a new run from one local Markdown or text source. The standard allocator chooses a non-colliding date/sequence/slug ID:

```powershell
python -m fanglei --runs-dir runs ingest .\source.md
```

Continue through analysis and research:

```powershell
python -m fanglei --runs-dir runs analyze RUN_ID
python -m fanglei --runs-dir runs research RUN_ID --provider tavily
```

`research` can stop after `search`, `source_fetch`, `source_selection`, `factcheck`, or `research_synthesis`. The real search provider reads `TAVILY_API_KEY` from the process environment; `--provider mock` is deterministic test input. Content planning supports `mock` or `deepseek`; the latter reads its key and model settings from the process environment.

Create approved content and visual artifacts with the existing commands:

```powershell
python -m fanglei --runs-dir runs plan-content RUN_ID --provider deepseek
python -m fanglei --runs-dir runs visual-plan RUN_ID
python -m fanglei --runs-dir runs storyboard RUN_ID
```

Review `facts.json`, `angle.md`, `script.json`, and `script.md` before downstream voice work. Native facts 2.1 and 2.2 use `docs/v0.2/native-facts-2.1.schema.json` and `docs/v0.2/native-facts-2.2.schema.json`. The existing imported formal facts 2.0 and script contracts remain in `docs/v0.2/facts.schema.json` and `docs/v0.3/script-contract.schema.json`; checkpoint-imported facts 2.1 use `docs/v0.2/checkpoint-import-facts-2.1.schema.json`.

## Production narration and voice review

`generate-voice` requires existing valid `narration.json` and `narration.txt`. The current CLI creates those artifacts through the narration-generation stage of `prepare-renderer`; stop at that stage so no fake audio or alignment is produced:

```powershell
python -m fanglei --runs-dir runs prepare-renderer RUN_ID --stop-after narration_generation
```

`prepare-renderer` only accepts fake providers. It requires the run's script and storyboard, and its later outputs must not be treated as production audio or measured alignment.

Use the already configured production provider and approved speaker. Provider credentials/configuration are read from environment variables (`VOLCENGINE_TTS_API_KEY`, `VOLCENGINE_TTS_SPEAKER`, `VOLCENGINE_TTS_RESOURCE_ID`, or the Azure equivalents); do not put secrets on the command line.

```powershell
python -m fanglei --runs-dir runs generate-voice RUN_ID --provider volcengine --voice-id $env:VOLCENGINE_TTS_SPEAKER --language zh-CN --speaking-rate 1.0 --pitch-semitones 0 --volume-gain-db 0
```

The command validates audio format and quality and writes `audio/narration.wav`, `audio/metadata.json`, and `audio/quality.json`. Inspect duration, peak/RMS, voiced duration/ratio, provider, speaker, and SHA-256 in those artifacts, then listen to the WAV. Continue only after the human review confirms voice, rate, pauses, and number pronunciation:

```powershell
python -m fanglei --runs-dir runs approve-voice RUN_ID --confirm-voice --confirm-speaking-rate --confirm-pauses --confirm-number-pronunciation --reviewer REVIEWER
```

`--force` on `generate-voice` regenerates audio and invalidates downstream approvals/artifacts. Use it only for an intentional regeneration; review the new audio hash again.

## Alignment, timeline, renderer, and QA

The real alignment path is a Python API, not a CLI command: `run_alignment_candidate(run_id, runs_dir, provider)` in `src/fanglei/audio_alignment.py`. It requires production-eligible audio, current voice approval, matching audio hashes/duration, and a production alignment provider with pinned model provenance. The local WhisperX adapter requires a configured engine and explicit `RUN_WHISPERX_ALIGNMENT=1` opt-in. Do not use `prepare-renderer` for production alignment; the CLI hard-codes fake providers.

The candidate path writes `alignment_candidate.json`. The current review helper, `promote_alignment(...)` in `src/fanglei/alignment_calibration.py`, handles only a narrowly scoped, hash-bound human review of an `ALIGNMENT_TEXT_MISMATCH`; it does not expose a general CLI promotion command. Keep timeline and subtitle work blocked until a valid final `alignment.json` exists.

`prepare-renderer` runs the deterministic fake path through narration, fake audio/alignment, timeline, Nikola project construction, and render preflight. Its `preflight_report.json` and `render_qa.json` are preflight outputs, not final-video QA. The inspected CLI has no final MP4 render command. `subtitle` requires valid script and alignment artifacts; `master-audio` requires production audio, passing quality, and voice approval. V1b renderer adaptation is available as a Python function and requires the V1a project plus final subtitle and mastered-audio artifacts.

When a stage fails, inspect `run.json` and the failed artifact/gate first. Retry only the owning stage with its documented `--force` or `--force-stage` option after correcting the input; the registry marks changed descendants stale. Do not promote artifacts whose dependencies are stale or whose hashes do not match.

## Approved checkpoint import

The importer currently has no CLI command. Call its Python API with the original approved checkpoint object and a stable source-cache directory:

```python
from pathlib import Path
from fanglei.checkpoint_import import CheckpointImporter

importer = CheckpointImporter(Path("runs"), Path(".checkpoint-source-cache"))
staged = importer.stage(checkpoint)
print(staged.status, staged.staging_dir, staged.gates)
```

The checkpoint envelope must explicitly identify approval, version, claims, evidence, angle, script, research, and official HTTPS source URLs. Required `AngleCandidate`, facts, and script fields must be present in approved input; never invent or default them. Staging is written under `.checkpoint-staging/cp-<fingerprint-prefix>`. Review `checkpoint_fingerprint.json`, `id_mapping.json`, `import_manifest.json`, and `gates.json` when present. A failed gate means stop; no production run is created. Only after `stage()` reports all gates passed should `import_checkpoint(checkpoint, run_title=...)` be used to promote the complete package to `runs/<run_id>/`.

The first successful capture of a source URL is pinned by content hash. Reimports reuse the capture. If the source cannot be recovered, an excerpt/locator cannot be verified, or the URL content changes, stop on the provenance error and preserve the existing capture; do not silently refresh it or alter the evidence basis. A failed staging package is useful for diagnosis and can remain in `.checkpoint-staging/`; it is not a production run.
