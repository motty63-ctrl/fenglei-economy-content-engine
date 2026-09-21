"""Command-line interface for the Phase 1 pipeline."""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Annotated

import typer

from fanglei.errors import FangleiError
from fanglei.providers.mock import MockAnalysisProvider
from fanglei.stages.analyze import analyze_run
from fanglei.stages.ingest import ingest_file, ingest_text
from fanglei.pipeline import run_v02_pipeline
from fanglei.providers.http_fetch import HttpDocumentFetcher
from fanglei.providers.search import TavilySearchProvider
from fanglei.providers.mock_research import MockDocumentFetcher, MockSearchProvider
from fanglei.security import safe_error_message
from fanglei.content_pipeline import run_content_pipeline
from fanglei.providers.content import DeepSeekContentPlanningProvider, MockContentPlanningProvider
from fanglei.providers.visual import DeterministicVisualPlanningProvider
from fanglei.visual_pipeline import run_visual_pipeline
from fanglei.providers.alignment import FakeAlignmentProvider
from fanglei.providers.narration import FakeNarrationProvider
from fanglei.render_preflight import FakeRendererProbe
from fanglei.v05_pipeline import run_v05_pipeline
from fanglei.v05_pipeline import run_voice_generation, approve_voice_run
from fanglei.provider_factory import build_narration_provider
from fanglei.v05_models import NarrationSynthesisConfig
from fanglei.v1b_pipeline import run_audio_mastering, run_subtitle_generation
from fanglei.providers.mastering import FFmpegLoudnormMasteringEngine


app = typer.Typer(no_args_is_help=True, help="Build durable research artifacts from economic source text.")


@app.callback()
def configure(
    ctx: typer.Context,
    runs_dir: Annotated[Path, typer.Option(help="Directory that stores independent runs.")] = Path("runs"),
) -> None:
    ctx.obj = {"runs_dir": runs_dir}


def _fail(error: FangleiError) -> None:
    typer.echo(f"Error: {safe_error_message(error)}", err=True)
    raise typer.Exit(code=error.exit_code)


@app.command("ingest")
def ingest_command(
    ctx: typer.Context,
    source: Annotated[Path | None, typer.Argument(help="Local .txt or .md file.")] = None,
    text: Annotated[str | None, typer.Option("--text", help="Text pasted as one argument.")] = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read multiline text from standard input.")] = False,
) -> None:
    modes = int(source is not None) + int(text is not None) + int(stdin)
    if modes != 1:
        typer.echo("Error: provide exactly one of FILE, --text, or --stdin", err=True)
        raise typer.Exit(code=2)
    runs_dir: Path = ctx.obj["runs_dir"]
    try:
        if source is not None:
            run_dir = ingest_file(source, runs_dir)
        else:
            run_dir = ingest_text(sys.stdin.read() if stdin else text or "", runs_dir)
    except FangleiError as error:
        _fail(error)
    typer.echo(f"Created run: {run_dir.name}")
    typer.echo(f"Run directory: {run_dir.resolve()}")
    typer.echo(f"Artifact: {run_dir / 'source.md'}")
    typer.echo(f"Next: python -m fanglei analyze {run_dir.name}")


@app.command("analyze")
def analyze_command(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="Existing run ID.")],
    force: Annotated[bool, typer.Option("--force", help="Snapshot and replace existing analysis artifacts.")] = False,
) -> None:
    runs_dir: Path = ctx.obj["runs_dir"]
    manifest_path = runs_dir / run_id / "run.json"
    before = manifest_path.read_bytes() if manifest_path.is_file() else None
    try:
        run_dir = analyze_run(run_id, runs_dir, MockAnalysisProvider(), force=force)
    except FangleiError as error:
        _fail(error)
    after = (run_dir / "run.json").read_bytes()
    if before is not None and before == after and not force:
        typer.echo(f"Analysis already current: {run_id}")
    else:
        typer.echo(f"Analyzed run: {run_id}")
    typer.echo(f"Artifact: {run_dir / 'questions.json'}")


@app.command("research")
def research_command(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="Existing analyzed run ID.")],
    stop_after: Annotated[
        str | None,
        typer.Option("--stop-after", help="Stop after search, source_fetch, source_selection, factcheck, or research_synthesis."),
    ] = None,
    force_stage: Annotated[
        str | None,
        typer.Option("--force-stage", help="Explicitly rerun one owner stage and invalidate descendants."),
    ] = None,
    provider_name: Annotated[str, typer.Option("--provider", help="tavily (default) or mock.")] = "tavily",
) -> None:
    stages = {"search", "source_fetch", "source_selection", "factcheck", "research_synthesis"}
    if stop_after is not None and stop_after not in stages:
        typer.echo("Error: invalid --stop-after stage", err=True)
        raise typer.Exit(code=2)
    if force_stage is not None and force_stage not in stages:
        typer.echo("Error: invalid --force-stage stage", err=True)
        raise typer.Exit(code=2)
    if provider_name not in {"tavily", "mock"}:
        typer.echo("Error: --provider must be tavily or mock", err=True)
        raise typer.Exit(code=2)
    try:
        provider = MockSearchProvider() if provider_name == "mock" else TavilySearchProvider(os.environ.get("TAVILY_API_KEY", ""))
        fetcher = MockDocumentFetcher() if provider_name == "mock" else HttpDocumentFetcher()
        run_dir = run_v02_pipeline(
            run_id,
            ctx.obj["runs_dir"],
            provider,
            fetcher,
            stop_after=stop_after,
            force_stage=force_stage,
        )
    except FangleiError as error:
        _fail(error)
    typer.echo(f"Research pipeline current: {run_id}")
    typer.echo(f"Run directory: {run_dir.resolve()}")


def _content_run(ctx: typer.Context, run_id: str, provider_name: str, speaking_rate: float,
                 stop_after: str | None = None, angle_id: str | None = None,
                 force_stage: str | None = None) -> Path:
    if provider_name == "mock":
        content_provider = MockContentPlanningProvider()
    elif provider_name == "deepseek":
        try:
            content_provider = DeepSeekContentPlanningProvider(
                os.environ.get("DEEPSEEK_API_KEY", ""),
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
                angle_temperature=float(os.environ.get("DEEPSEEK_ANGLE_TEMPERATURE", "0.6")),
                script_temperature=float(os.environ.get("DEEPSEEK_SCRIPT_TEMPERATURE", "0.2")),
                repair_temperature=float(os.environ.get("DEEPSEEK_REPAIR_TEMPERATURE", "0.0")),
            )
        except (FangleiError, ValueError) as error:
            _fail(error)
    else:
        typer.echo("Error: --provider must be mock or deepseek", err=True)
        raise typer.Exit(code=2)
    try:
        return run_content_pipeline(run_id, ctx.obj["runs_dir"], content_provider,
            stop_after=stop_after, angle_id=angle_id, speaking_rate=speaking_rate,
            force_stage=force_stage)
    except FangleiError as error:
        _fail(error)


@app.command("angles")
def angles_command(ctx: typer.Context, run_id: str, provider: str = "mock") -> None:
    run = _content_run(ctx, run_id, provider, 4.0, stop_after="angle_generation")
    typer.echo(f"Artifact: {run / 'angles.json'}")


@app.command("select-angle")
def select_angle_command(ctx: typer.Context, run_id: str, angle_id: str | None = None,
                         provider: str = "mock") -> None:
    run = _content_run(ctx, run_id, provider, 4.0, stop_after="angle_selection", angle_id=angle_id)
    typer.echo(f"Artifact: {run / 'angle.md'}")


@app.command("script")
def script_command(ctx: typer.Context, run_id: str, provider: str = "mock",
                   speaking_rate: float = 4.0) -> None:
    run = _content_run(ctx, run_id, provider, speaking_rate)
    typer.echo(f"Artifacts: {run / 'script.json'}, {run / 'script.md'}")


@app.command("plan-content")
def plan_content_command(ctx: typer.Context, run_id: str, provider: str = "mock",
                         speaking_rate: float = 4.0, angle_id: str | None = None,
                         force_stage: str | None = None) -> None:
    run = _content_run(ctx, run_id, provider, speaking_rate, angle_id=angle_id, force_stage=force_stage)
    typer.echo(f"Content pipeline current: {run_id}")
    typer.echo(f"Run directory: {run.resolve()}")


@app.command("visual-plan")
def visual_plan_command(ctx: typer.Context, run_id: str,
                        force: Annotated[bool, typer.Option("--force", help="Rerun semantic visual planning.")] = False) -> None:
    run = run_visual_pipeline(
        run_id, ctx.obj["runs_dir"], DeterministicVisualPlanningProvider(),
        stop_after="visual_planning", force_stage="visual_planning" if force else None,
    )
    typer.echo(f"Artifact: {run / 'visual_beats.json'}")


@app.command("storyboard")
def storyboard_command(
    ctx: typer.Context,
    run_id: str,
    force_stage: Annotated[str | None, typer.Option("--force-stage")] = None,
) -> None:
    run = run_visual_pipeline(
        run_id, ctx.obj["runs_dir"], DeterministicVisualPlanningProvider(), force_stage=force_stage,
    )
    typer.echo(f"Artifacts: {run / 'storyboard.json'}, {run / 'visual_plan.md'}")


@app.command("prepare-renderer")
def prepare_renderer_command(
    ctx: typer.Context,
    run_id: str,
    narration_provider: Annotated[str, typer.Option("--narration-provider")] = "fake",
    alignment_provider: Annotated[str, typer.Option("--alignment-provider")] = "fake",
    probe: Annotated[str, typer.Option("--probe")] = "fake",
    voice_id: Annotated[str, typer.Option("--voice-id")] = "fake-voice",
    stop_after: Annotated[str | None, typer.Option("--stop-after")] = None,
    force_stage: Annotated[str | None, typer.Option("--force-stage")] = None,
) -> None:
    if (narration_provider, alignment_provider, probe) != ("fake", "fake", "fake"):
        typer.echo("Error: V0.5 currently exposes only explicit fake providers", err=True)
        raise typer.Exit(code=2)
    run = run_v05_pipeline(
        run_id, ctx.obj["runs_dir"], FakeNarrationProvider(), FakeAlignmentProvider(),
        FakeRendererProbe(), voice_id=voice_id, stop_after=stop_after, force_stage=force_stage,
    )
    typer.echo(f"renderer_ready: {run_id}")
    typer.echo(f"Run directory: {run.resolve()}")


@app.command("generate-voice")
def generate_voice_command(
    ctx: typer.Context,
    run_id: str,
    provider: Annotated[str, typer.Option("--provider")] = "azure",
    voice_id: Annotated[str, typer.Option("--voice-id")] = "",
    language: Annotated[str, typer.Option("--language")] = "zh-CN",
    speaking_rate: Annotated[float, typer.Option("--speaking-rate")] = 1.0,
    pitch_semitones: Annotated[float, typer.Option("--pitch-semitones")] = 0.0,
    volume_gain_db: Annotated[float, typer.Option("--volume-gain-db")] = 0.0,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    if provider == "fake":
        typer.echo("PRODUCTION_PROVIDER_REQUIRED", err=True)
        raise typer.Exit(code=2)
    try:
        config = NarrationSynthesisConfig(
            voice_id=voice_id, language=language, speaking_rate=speaking_rate,
            pitch_semitones=pitch_semitones, volume_gain_db=volume_gain_db,
        )
        if not config.voice_id:
            raise ValueError("VOICE_ID_REQUIRED")
        run = run_voice_generation(run_id, ctx.obj["runs_dir"],
                                   build_narration_provider(provider), config, force=force)
    except Exception as error:
        typer.echo(f"Error: {safe_error_message(error)}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Voice review pending: {run / 'audio' / 'narration.wav'}")
    typer.echo(f"Audio quality: {run / 'audio' / 'quality.json'}")


@app.command("approve-voice")
def approve_voice_command(
    ctx: typer.Context, run_id: str,
    confirm_voice: Annotated[bool, typer.Option("--confirm-voice")] = False,
    confirm_speaking_rate: Annotated[bool, typer.Option("--confirm-speaking-rate")] = False,
    confirm_pauses: Annotated[bool, typer.Option("--confirm-pauses")] = False,
    confirm_number_pronunciation: Annotated[bool, typer.Option("--confirm-number-pronunciation")] = False,
    reviewer: Annotated[str, typer.Option("--reviewer")] = "human",
) -> None:
    try:
        run = approve_voice_run(run_id, ctx.obj["runs_dir"], reviewer=reviewer,
                                voice=confirm_voice, rate=confirm_speaking_rate,
                                pauses=confirm_pauses,
                                number_pronunciation=confirm_number_pronunciation)
    except Exception as error:
        typer.echo(f"Error: {safe_error_message(error)}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Voice approved for current audio hash: {run / 'audio' / 'review.json'}")


@app.command("subtitle")
def subtitle_command(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="Existing approved run ID.")],
    force: Annotated[bool, typer.Option("--force", help="Recompile subtitle artifact.")] = False,
) -> None:
    try:
        run = run_subtitle_generation(run_id, ctx.obj["runs_dir"], force=force)
    except Exception as error:
        typer.echo(f"Error: {safe_error_message(error)}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Artifact: {run / 'subtitle_track.json'}")


@app.command("master-audio")
def master_audio_command(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="Existing voice-approved run ID.")],
    force: Annotated[bool, typer.Option("--force", help="Regenerate mastered playback audio.")] = False,
) -> None:
    try:
        run = run_audio_mastering(run_id, ctx.obj["runs_dir"],
                                  FFmpegLoudnormMasteringEngine(), force=force)
    except Exception as error:
        typer.echo(f"Error: {safe_error_message(error)}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Artifacts: {run / 'audio' / 'mastered_narration.wav'}, {run / 'audio_mastering.json'}")
