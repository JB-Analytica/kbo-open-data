"""Shared fixtures: one real dlt load, reused by every assertion about its output.

The load runs for real -- synthetic zip in, DuckDB file out, no mocks and no credentials --
because the things worth asserting here (what dlt normalised a column to, what merge did on
a second run, what actually landed in the file) only exist after a real load.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pytest

from ingest import kbo_source
from tests.fixtures import synthetic_kbo


@dataclass(frozen=True)
class LoadedWarehouse:
    zip_path: Path
    duckdb_path: Path
    pipelines_dir: Path

    def load(self) -> None:
        import dlt

        pipeline = kbo_source.build_pipeline(
            dlt.destinations.duckdb(str(self.duckdb_path)), self.pipelines_dir
        )
        info = pipeline.run(kbo_source.kbo_source(self.zip_path))
        info.raise_on_failed_jobs()

    def query(self, sql: str) -> list[tuple]:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            return connection.execute(sql).fetchall()

    def tables(self) -> set[str]:
        rows = self.query(
            "select table_name from information_schema.tables "
            f"where table_schema = '{kbo_source.DATASET_NAME}'"
        )
        return {name for (name,) in rows}

    def columns(self, table: str) -> set[str]:
        rows = self.query(
            "select column_name from information_schema.columns "
            f"where table_schema = '{kbo_source.DATASET_NAME}' and table_name = '{table}'"
        )
        return {name for (name,) in rows}

    def row_counts(self) -> dict[str, int]:
        return {
            table: self.query(f'select count(*) from {kbo_source.DATASET_NAME}."{table}"')[0][0]
            for table in sorted(spec.table for spec in kbo_source.KBO_FILES)
        }


@pytest.fixture(scope="session")
def extract_zip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return synthetic_kbo.write_extract(tmp_path_factory.mktemp("extract") / "kbo.zip", count=120)


@pytest.fixture(scope="session")
def loaded(tmp_path_factory: pytest.TempPathFactory, extract_zip: Path) -> LoadedWarehouse:
    workdir = tmp_path_factory.mktemp("warehouse")
    warehouse = LoadedWarehouse(
        zip_path=extract_zip,
        duckdb_path=workdir / "kbo.duckdb",
        pipelines_dir=workdir / "pipelines",
    )
    warehouse.load()
    return warehouse
