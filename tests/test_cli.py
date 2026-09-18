"""The CLI surface: it must report a problem as a message and an exit code, not a stack."""

from __future__ import annotations

from pathlib import Path

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
