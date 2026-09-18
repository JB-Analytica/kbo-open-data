"""Configuration, and the one rule that matters: the load can only ever go local."""

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


def test_the_load_destination_is_always_local(tmp_path: Path) -> None:
    """DESTINATION says where the marts are published, never where the raw layer lands.

    41 million raw rows, 770,434 of them natural persons, must not be reachable from the
    loader at all -- so `motherduck` here still resolves to the local DuckDB file.
    """
    local = tmp_path / "kbo.duckdb"
    for destination in ("duckdb", "motherduck"):
        settings = Settings(
            destination=destination, duckdb_path=local, motherduck_token="not-a-real-token"
        )
        assert dlt_destination(settings).config_params["credentials"] == str(local)


def test_missing_zip_says_what_to_do() -> None:
    with pytest.raises(ConfigError, match="KBO_ZIP"):
        Settings().require_zip()

    with pytest.raises(ConfigError, match="does not exist"):
        Settings(kbo_zip=Path("/nope/kbo.zip")).require_zip()
