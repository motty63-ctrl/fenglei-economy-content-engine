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


app = typer.Typer(no_args_is_help=True, help="Build durable research artifacts from economic source text.")


@app.callback()
def configure(
    ctx: typer.Context,
    runs_dir: Annotated[Path, typer.Option(help="Directory that stores independent runs.")] = Path("runs"),
) -> None:
    ctx.obj = {"runs_dir": runs_dir}


def _fail(error: FangleiError) -> None:
    typer.echo(f"Error: {error}", err=True)
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
