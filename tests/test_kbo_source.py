"""What the loaded warehouse must look like for dbt, and what must not be in it."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import pytest

from ingest import kbo_source
from tests.conftest import LoadedWarehouse
from tests.fixtures.synthetic_kbo import SNAPSHOT_DATE

DLT_COLUMNS = {"_dlt_id", "_dlt_load_id"}
DAY_FIRST = re.compile(r"^\d{2}-\d{2}-\d{4}$")


def test_every_table_is_created_and_populated(loaded: LoadedWarehouse) -> None:
    expected = {spec.table for spec in kbo_source.KBO_FILES}
    assert expected <= loaded.tables()
    assert all(count > 0 for count in loaded.row_counts().values())


@pytest.mark.parametrize("spec", kbo_source.KBO_FILES, ids=lambda spec: spec.table)
def test_only_allowlisted_columns_are_loaded(
    loaded: LoadedWarehouse, spec: kbo_source.KboFile
) -> None:
    """The privacy claim, asserted against KBO_FILES rather than a hand-written list.

    Adding a column to the allowlist without thinking therefore cannot pass silently: it
    has to be a deliberate edit to the table that the README points at.
    """
    assert loaded.columns(spec.table) - DLT_COLUMNS == set(spec.columns.values())


def test_lineage_columns_are_on(loaded: LoadedWarehouse) -> None:
    """dbt source freshness reads _dlt_load_id; without it nothing records arrival time."""
    assert loaded.columns("enterprise") >= DLT_COLUMNS


def test_every_loaded_column_is_text(loaded: LoadedWarehouse) -> None:
    """Typing is dbt's job. dlt inferring a type over a day-first date is the classic bite."""
    for spec in kbo_source.KBO_FILES:
        types = loaded.query(
            "select column_name, data_type from information_schema.columns "
            f"where table_schema = '{kbo_source.DATASET_NAME}' and table_name = '{spec.table}' "
            f"and column_name not in ('_dlt_id', '_dlt_load_id')"
        )
        assert {t for _, t in types} == {"VARCHAR"}, f"{spec.table}: {types}"


def test_excluded_files_are_never_loaded(loaded: LoadedWarehouse) -> None:
    assert loaded.tables() & {"denomination", "contact"} == set()


def test_no_personal_data_anywhere_in_the_database(loaded: LoadedWarehouse) -> None:
    """Scan every text column of every table for the fixture's fake names and e-mails.

    A table-name check alone would miss a stray column, so this looks at the values.
    """
    text_columns = loaded.query(
        "select table_name, column_name from information_schema.columns "
        f"where table_schema = '{kbo_source.DATASET_NAME}' and data_type = 'VARCHAR'"
    )
    for table, column in text_columns:
        hits = loaded.query(
            f'select count(*) from {kbo_source.DATASET_NAME}."{table}" '
            f"where \"{column}\" like '%Fictief Bedrijf%' or \"{column}\" like '%example.invalid%'"
        )[0][0]
        assert hits == 0, f"personal data from the fixture reached {table}.{column}"


def test_reloading_the_same_zip_changes_nothing(loaded: LoadedWarehouse) -> None:
    """Merge on the primary key: the daily update file re-sends rows we already have."""
    before = loaded.row_counts()
    loaded.load()
    assert loaded.row_counts() == before


def test_dates_land_as_untouched_day_first_text(loaded: LoadedWarehouse) -> None:
    rows = loaded.query(
        f"select start_date from {kbo_source.DATASET_NAME}.enterprise where start_date <> ''"
    )
    assert rows
    assert all(isinstance(value, str) and DAY_FIRST.match(value) for (value,) in rows)


def test_snapshot_date_is_parsed_day_first(extract_zip: Path) -> None:
    """07-09-2026 is 7 September, not 9 July. dbt relies on this being unambiguous."""
    assert kbo_source.snapshot_date(extract_zip) == SNAPSHOT_DATE == date(2026, 9, 7)


def _rewrite_zip(source: Path, target: Path, member: str, drop_column: str) -> Path:
    """Copy the extract, minus one column of one file."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as rewritten:
        for name in original.namelist():
            data = original.read(name)
            if name == member:
                reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
                fields = [f for f in (reader.fieldnames or []) if f != drop_column]
                buffer = io.StringIO(newline="")
                writer = csv.DictWriter(
                    buffer,
                    fields,
                    extrasaction="ignore",
                    quoting=csv.QUOTE_ALL,
                    lineterminator="\r\n",
                )
                writer.writeheader()
                writer.writerows(reader)
                data = buffer.getvalue().encode("utf-8")
            rewritten.writestr(name, data)
    return target


def test_missing_allowed_column_fails_loudly(extract_zip: Path, tmp_path: Path) -> None:
    broken = _rewrite_zip(extract_zip, tmp_path / "broken.zip", "enterprise.csv", "JuridicalForm")
    with pytest.raises(kbo_source.ExtractError) as excinfo:
        list(kbo_source._rows(broken, _spec_for("enterprise")))
    assert "enterprise.csv" in str(excinfo.value)
    assert "JuridicalForm" in str(excinfo.value)


def test_unexpected_extra_column_is_ignored(extract_zip: Path) -> None:
    """enterprise.csv really does carry JuridicalFormCAC; it must not reach the rows."""
    spec = _spec_for("enterprise")
    first = next(iter(kbo_source._rows(extract_zip, spec)))
    assert set(first) == set(spec.columns.values())


def _spec_for(table: str) -> kbo_source.KboFile:
    return next(spec for spec in kbo_source.KBO_FILES if spec.table == table)
