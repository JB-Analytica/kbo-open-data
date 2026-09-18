"""Configuration, and the one rule that matters: never guess a destination account."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingest.config import ConfigError, Settings, dlt_destination


def test_defaults_are_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("DESTINATION", "DUCKDB_PATH", "KBO_ZIP", "MOTHERDUCK_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env(env_file=tmp_path / "absent.env")
    assert settings.destination == "duckdb"
    assert settings.duckdb_path == Path("kbo.duckdb")
    assert settings.motherduck_database == "kbo"


def test_unknown_destination_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DESTINATION", "snowflake")
    with pytest.raises(ConfigError, match="not supported"):
        Settings.from_env(env_file=tmp_path / "absent.env")


def test_motherduck_without_a_token_is_an_error() -> None:
    settings = Settings(destination="motherduck")
    with pytest.raises(ConfigError, match="MOTHERDUCK_TOKEN"):
        dlt_destination(settings)


def test_missing_zip_says_what_to_do() -> None:
    with pytest.raises(ConfigError, match="KBO_ZIP"):
        Settings().require_zip()

    with pytest.raises(ConfigError, match="does not exist"):
        Settings(kbo_zip=Path("/nope/kbo.zip")).require_zip()
