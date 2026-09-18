"""The publish step, exercised for real against a second local DuckDB file.

No MotherDuck, no token, no network: the target is a parameter precisely so this path is
tested rather than hoped for. What is asserted is what the Flight depends on -- the marts
arrive, the row counts arrive with them, and a second publish overwrites rather than
appends or fails.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ingest.config import ConfigError, Settings
from ingest.publish import (
    PublishError,
    PublishTarget,
    motherduck_target,
    publish_marts,
)


def _build_source(path: Path, rows: dict[str, int]) -> Path:
    """A miniature warehouse: a raw schema that must not travel, and some marts."""
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA kbo_raw")
        connection.execute("CREATE TABLE kbo_raw.enterprise AS SELECT 1 AS enterprise_number")
        connection.execute("CREATE SCHEMA marts")
        for name, count in rows.items():
            connection.execute(
                f'CREATE TABLE marts."{name}" AS '
                f"SELECT i AS bucket, i * 10 AS enterprise_count FROM range({count}) t(i)"
            )
    return path


def _target_tables(path: Path, schema: str) -> dict[str, int]:
    with duckdb.connect(str(path), read_only=True) as connection:
        names = [
            name
            for (name,) in connection.execute(
                "SELECT table_name FROM duckdb_tables() WHERE schema_name = ?", [schema]
            ).fetchall()
        ]
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{schema}"."{name}"').fetchone()[0]
            for name in names
        }


def test_only_the_marts_travel(tmp_path: Path) -> None:
    source = _build_source(tmp_path / "source.duckdb", {"agg_one": 3, "agg_two": 7})
    target_path = tmp_path / "published.duckdb"

    published = publish_marts(source, PublishTarget.local(target_path))

    assert [(mart.name, mart.row_count) for mart in published] == [
        ("agg_one", 3),
        ("agg_two", 7),
    ]
    assert _target_tables(target_path, "marts") == {"agg_one": 3, "agg_two": 7}
    # The raw layer is the entire point of publishing this way: it must not be there.
    assert _target_tables(target_path, "kbo_raw") == {}


def test_a_new_mart_needs_no_code_change(tmp_path: Path) -> None:
    source = _build_source(tmp_path / "source.duckdb", {"agg_one": 1, "agg_sixth": 2})
    target_path = tmp_path / "published.duckdb"

    published = publish_marts(source, PublishTarget.local(target_path))

    assert {mart.name for mart in published} == {"agg_one", "agg_sixth"}


def test_republishing_replaces_rather_than_appends(tmp_path: Path) -> None:
    source_path = _build_source(tmp_path / "source.duckdb", {"agg_one": 4})
    target_path = tmp_path / "published.duckdb"
    target = PublishTarget.local(target_path)

    publish_marts(source_path, target)
    again = publish_marts(source_path, target)

    assert [(mart.name, mart.row_count) for mart in again] == [("agg_one", 4)]
    assert _target_tables(target_path, "marts") == {"agg_one": 4}


def test_a_rebuilt_mart_overwrites_the_published_one(tmp_path: Path) -> None:
    source_path = _build_source(tmp_path / "source.duckdb", {"agg_one": 4})
    target_path = tmp_path / "published.duckdb"
    publish_marts(source_path, PublishTarget.local(target_path))

    with duckdb.connect(str(source_path)) as connection:
        connection.execute("CREATE OR REPLACE TABLE marts.agg_one AS SELECT 1 AS bucket")

    published = publish_marts(source_path, PublishTarget.local(target_path))
    assert [(mart.name, mart.row_count) for mart in published] == [("agg_one", 1)]
    assert _target_tables(target_path, "marts") == {"agg_one": 1}


def test_no_marts_schema_says_to_build_first(tmp_path: Path) -> None:
    source_path = tmp_path / "source.duckdb"
    with duckdb.connect(str(source_path)) as connection:
        connection.execute("CREATE SCHEMA kbo_raw")
        connection.execute("CREATE TABLE kbo_raw.enterprise AS SELECT 1 AS enterprise_number")

    with pytest.raises(PublishError, match="Run the build first"):
        publish_marts(source_path, PublishTarget.local(tmp_path / "published.duckdb"))
    assert not (tmp_path / "published.duckdb").exists()


def test_an_empty_marts_schema_says_to_build_first(tmp_path: Path) -> None:
    source_path = tmp_path / "source.duckdb"
    with duckdb.connect(str(source_path)) as connection:
        connection.execute("CREATE SCHEMA marts")

    with pytest.raises(PublishError, match="nothing to publish"):
        publish_marts(source_path, PublishTarget.local(tmp_path / "published.duckdb"))


def test_a_missing_warehouse_says_to_build_first(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="no warehouse"):
        publish_marts(tmp_path / "absent.duckdb", PublishTarget.local(tmp_path / "out.duckdb"))


def test_motherduck_without_a_token_is_an_error() -> None:
    with pytest.raises(ConfigError, match="MOTHERDUCK_TOKEN"):
        motherduck_target(Settings(destination="motherduck"))


def test_motherduck_with_a_token_targets_the_named_database() -> None:
    settings = Settings(
        destination="motherduck", motherduck_token="not-a-real-token", motherduck_database="kbo_ci"
    )
    target = motherduck_target(settings)
    assert target.is_motherduck
    assert target.database == "kbo_ci"
    # The token is never part of what is attached, because DuckDB echoes that into errors.
    assert "not-a-real-token" not in target.attach_spec
    assert str(target) == "md:kbo_ci"


def test_a_target_spec_is_parsed_as_motherduck_or_a_file(tmp_path: Path) -> None:
    assert PublishTarget.parse("md:kbo").is_motherduck
    assert not PublishTarget.parse(str(tmp_path / "out.duckdb")).is_motherduck
    with pytest.raises(PublishError, match="md:<database>"):
        PublishTarget.parse("md:")
