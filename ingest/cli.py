"""`kbo` -- the extract-and-load commands, plus the publish step.

The load always writes to a local DuckDB file; `kbo publish` is the only command that
talks to a cloud account, and it moves the five aggregate marts and nothing else.
"""

from __future__ import annotations

import dataclasses
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from ingest.config import REPO_ROOT, Settings

app = typer.Typer(
    name="kbo",
    help="Load the Belgian company register (KBO Open Data) into DuckDB, and publish "
    "the aggregate marts.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

DEFAULT_DEMO_ZIP = Path("data/raw/KboOpenData_SYNTHETIC_Full.zip")


def _show_ingest_logs() -> None:
    """Send `ingest`'s own INFO lines to stderr.

    The load picks replace or merge from the extract itself, and a silent switch between
    the two is the kind of surprise that is only noticed a warehouse later. dlt's own
    logging is left alone.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    ingest_logger = logging.getLogger("ingest")
    ingest_logger.addHandler(handler)
    ingest_logger.setLevel(logging.INFO)


def _fail(message: str) -> typer.Exit:
    """A configuration or extract problem is the user's to fix, so print it, not a stack."""
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


@app.command()
def load(
    zip_path: Annotated[
        Path | None,
        typer.Option("--zip", help="Extract to load. Defaults to KBO_ZIP from the environment."),
    ] = None,
) -> None:
    """Load the KBO extract into the `kbo_raw` schema."""
    from ingest import kbo_source

    _show_ingest_logs()
    settings = Settings.from_env()
    if zip_path is not None:
        settings = dataclasses.replace(settings, kbo_zip=zip_path)
    try:
        info = kbo_source.run(settings)
    except Exception as exc:
        raise _fail(str(exc)) from exc
    typer.echo(str(info))


@app.command()
def publish(
    target: Annotated[
        str | None,
        typer.Option(
            "--to",
            help="Target for the marts: md:<database>, or a path to a DuckDB file. "
            "Defaults to MotherDuck when DESTINATION=motherduck.",
        ),
    ] = None,
    source: Annotated[
        Path | None,
        typer.Option("--from", help="Warehouse to publish from. Defaults to DUCKDB_PATH."),
    ] = None,
) -> None:
    """Copy the aggregate marts to the published database. Raw data never moves."""
    from ingest import publish as publish_module

    try:
        settings = Settings.from_env()
        source_path = source if source is not None else settings.duckdb_path
        if target is not None:
            destination = publish_module.PublishTarget.parse(target)
        elif settings.publishes_to_motherduck:
            destination = publish_module.motherduck_target(settings)
        else:
            raise _fail(
                f"DESTINATION={settings.destination} keeps the marts local, so there is "
                "nothing to publish. Set DESTINATION=motherduck (with MOTHERDUCK_TOKEN) "
                "or pass --to md:<database> or --to <path to a DuckDB file>."
            )
        marts = publish_module.publish_marts(
            source_path, destination, motherduck_token=settings.motherduck_token
        )
    except typer.Exit:
        raise
    except Exception as exc:
        raise _fail(str(exc)) from exc

    for mart in marts:
        typer.echo(f"{mart.name}\t{mart.row_count}")
    typer.echo(f"published {len(marts)} marts to {destination}")


@app.command()
def fetch(
    remote_name: Annotated[str, typer.Argument(help="File name in the KBO SFTP drop.")],
    destination_dir: Annotated[Path, typer.Option("--into")] = Path("data/raw"),
) -> None:
    """Fetch a daily update file over SFTP (needs access granted by FOD Economie)."""
    from ingest import sftp

    try:
        path = sftp.fetch(Settings.from_env(), remote_name, destination_dir)
    except Exception as exc:
        raise _fail(str(exc)) from exc
    typer.echo(str(path))


@app.command("snapshot-date")
def snapshot_date_command(
    zip_path: Annotated[Path | None, typer.Option("--zip", help="Defaults to KBO_ZIP.")] = None,
) -> None:
    """Print the extract's snapshot date, without loading anything."""
    from ingest import kbo_source

    try:
        settings = Settings.from_env()
        path = zip_path if zip_path is not None else settings.require_zip()
        typer.echo(kbo_source.snapshot_date(path).isoformat())
    except Exception as exc:
        raise _fail(str(exc)) from exc


@app.command("demo-extract")
def demo_extract(
    path: Annotated[Path, typer.Argument(help="Where to write the zip.")] = DEFAULT_DEMO_ZIP,
    count: Annotated[int, typer.Option(help="Number of enterprises.")] = 400,
) -> None:
    """Write a synthetic extract, so the pipeline can be run without registering with KBO."""
    # The fixture lives in tests/, which ships with the repo but not with the wheel, and a
    # console script does not put the working directory on sys.path. Add the repo root so
    # `kbo demo-extract` works from any directory in a clone, and say so plainly if this
    # is an installed wheel with no tests/ beside it.
    if not (REPO_ROOT / "tests" / "fixtures" / "synthetic_kbo.py").exists():
        raise _fail(
            "The synthetic extract generator ships with the repository, not with the "
            "installed package. Run this from a clone of kbo-open-data."
        )
    sys.path.insert(0, str(REPO_ROOT))
    from tests.fixtures import synthetic_kbo

    typer.echo(str(synthetic_kbo.write_extract(path, count=count)))


if __name__ == "__main__":  # pragma: no cover
    app()
