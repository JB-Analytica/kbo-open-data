"""The CLI surface: it must report a problem as a message and an exit code, not a stack."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from ingest.cli import app

runner = CliRunner()


def test_help_is_shown_without_arguments() -> None:
    result = runner.invoke(app, [])
    assert "snapshot-date" in result.output
    assert "demo-extract" in result.output


def test_demo_extract_then_snapshot_date(tmp_path: Path) -> None:
    target = tmp_path / "demo.zip"
    assert runner.invoke(app, ["demo-extract", str(target), "--count", "5"]).exit_code == 0
    assert target.exists()

    result = runner.invoke(app, ["snapshot-date", "--zip", str(target)])
    assert result.exit_code == 0
    assert result.output.strip() == "2026-09-07"


def test_a_missing_zip_is_a_clean_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["snapshot-date", "--zip", str(tmp_path / "absent.zip")])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_publish_without_a_destination_says_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DESTINATION", "duckdb")
    result = runner.invoke(app, ["publish", "--from", str(tmp_path / "absent.duckdb")])
    assert result.exit_code == 1
    assert "nothing to publish" in result.output


def test_publish_to_a_local_file_reports_every_mart(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    with duckdb.connect(str(source)) as connection:
        connection.execute("CREATE SCHEMA marts")
        connection.execute("CREATE TABLE marts.agg_one AS SELECT * FROM range(3)")

    target = tmp_path / "published.duckdb"
    result = runner.invoke(app, ["publish", "--from", str(source), "--to", str(target)])
    assert result.exit_code == 0, result.output
    assert "agg_one\t3" in result.output
    assert "published 1 marts" in result.output


def test_publish_from_an_unbuilt_warehouse_is_a_clean_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["publish", "--from", str(tmp_path / "absent.duckdb"), "--to", str(tmp_path / "o.duckdb")],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
