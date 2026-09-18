"""The KBO extract, read out of the downloaded zip and loaded into DuckDB with dlt.

The one thing to understand here is `KBO_FILES`. KBO ships natural persons (sole traders)
whose name, street and e-mail address are personal data. This module therefore reads a
**column-level allowlist**: only the files listed below are opened, and only the columns
listed on each of them are ever pulled out of the archive. `denomination.csv` (company and
person names) and `contact.csv` (e-mail, phone, web) are absent on purpose -- nothing
downstream needs them, so they are never opened at all. Everything else about this module
is plumbing; the table below is the privacy claim.

Every column lands as TEXT. KBO writes dates day-first (`31-12-2026`), and letting dlt
infer a type turns that into either a wrong date or a failed load. dbt casts in staging.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import dlt
from dlt.common.pipeline import LoadInfo

from ingest.config import Settings, dlt_destination

# The pyarrow/parquet path does not add lineage columns unless asked, and dbt source
# freshness reads `_dlt_load_id`. Set it here rather than in .dlt/config.toml so the
# setting travels with the code and applies from any working directory, tests included.
os.environ.setdefault("NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_LOAD_ID", "true")
os.environ.setdefault("NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_ID", "true")

PIPELINE_NAME = "kbo"
DATASET_NAME = "kbo_raw"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PIPELINES_DIR = REPO_ROOT / ".dlt" / "pipelines"

META_FILE = "meta.csv"
SNAPSHOT_DATE_VARIABLE = "SnapshotDate"
KBO_DATE_FORMAT = "%d-%m-%Y"


class ExtractError(RuntimeError):
    """The zip is not a KBO extract we recognise. The message names file and column."""


def _snake(source_column: str) -> str:
    """`TypeOfEnterprise` -> `type_of_enterprise`, matching dlt's snake_case normaliser."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", source_column).lower()


@dataclass(frozen=True)
class KboFile:
    filename: str
    table: str
    # Source header names, spelled exactly as KBO spells them. Nothing outside this
    # tuple is read from the file, let alone loaded.
    source_columns: tuple[str, ...]
    # Normalised names, because a primary key is asserted against what lands.
    primary_key: tuple[str, ...]

    @property
    def columns(self) -> dict[str, str]:
        """Source header name -> the column name that lands in the warehouse."""
        return {source: _snake(source) for source in self.source_columns}


# ---------------------------------------------------------------------------------------
# The allowlist. Add a column here and it is loaded; that is the only way one gets loaded.
# ---------------------------------------------------------------------------------------
KBO_FILES: tuple[KboFile, ...] = (
    KboFile(
        filename="meta.csv",
        table="meta",
        source_columns=("Variable", "Value"),
        primary_key=("variable",),
    ),
    KboFile(
        filename="code.csv",
        table="code",
        source_columns=("Category", "Code", "Language", "Description"),
        primary_key=("category", "code", "language"),
    ),
    KboFile(
        filename="enterprise.csv",
        table="enterprise",
        # JuridicalFormCAC is also in the file and is deliberately dropped.
        source_columns=(
            "EnterpriseNumber",
            "Status",
            "JuridicalSituation",
            "TypeOfEnterprise",
            "JuridicalForm",
            "StartDate",
        ),
        primary_key=("enterprise_number",),
    ),
    KboFile(
        filename="establishment.csv",
        table="establishment",
        source_columns=("EstablishmentNumber", "StartDate", "EnterpriseNumber"),
        primary_key=("establishment_number",),
    ),
    KboFile(
        filename="address.csv",
        table="address",
        # Street, house number, box, municipality and country stay in the zip: for a sole
        # trader they are a home address. A postcode is all the aggregates need.
        source_columns=("EntityNumber", "TypeOfAddress", "Zipcode", "DateStrikingOff"),
        primary_key=("entity_number", "type_of_address"),
    ),
    KboFile(
        filename="activity.csv",
        table="activity",
        source_columns=(
            "EntityNumber",
            "ActivityGroup",
            "NaceVersion",
            "NaceCode",
            "Classification",
        ),
        # An entity can hold the same NACE code under several groups and classifications,
        # so the whole row is the key.
        primary_key=(
            "entity_number",
            "activity_group",
            "nace_version",
            "nace_code",
            "classification",
        ),
    ),
    KboFile(
        filename="branch.csv",
        table="branch",
        source_columns=("Id", "StartDate", "EnterpriseNumber"),
        primary_key=("id",),
    ),
)

# Named so the exclusion is greppable and testable, not just an absence.
NEVER_READ = ("denomination.csv", "contact.csv")


@contextmanager
def _reader(zip_path: Path, filename: str) -> Iterator[csv.DictReader]:
    """Open one member of the zip as a csv.DictReader.

    A real extract is gigabytes, so this never materialises a file: `zipfile.open` gives a
    stream, `TextIOWrapper` decodes it (utf-8-sig, because KBO leads some files with a BOM)
    and `csv.DictReader` handles the full quoting and the CRLF line endings.
    """
    with zipfile.ZipFile(zip_path) as archive:
        try:
            member = archive.open(filename)
        except KeyError as exc:
            raise ExtractError(
                f"{filename} is missing from {zip_path}. Is this a KBO Open Data zip?"
            ) from exc
        with member, io.TextIOWrapper(member, encoding="utf-8-sig", newline="") as text:
            yield csv.DictReader(text)


def _require_columns(spec: KboFile, header: Sequence[str] | None) -> None:
    present = set(header or ())
    missing = [column for column in spec.source_columns if column not in present]
    if missing:
        raise ExtractError(
            f"{spec.filename} is missing required column(s) {', '.join(missing)}. "
            f"Found: {', '.join(sorted(present)) or '(no header)'}. "
            "The KBO layout changed, or this is not a KBO extract."
        )


def _rows(zip_path: Path, spec: KboFile) -> Iterator[dict[str, str]]:
    """Yield allowlisted columns only. Extra columns in the file are ignored silently."""
    keep = spec.columns
    with _reader(zip_path, spec.filename) as reader:
        _require_columns(spec, reader.fieldnames)
        for row in reader:
            yield {target: row[source] or "" for source, target in keep.items()}


def _make_resource(zip_path: Path, spec: KboFile) -> Any:
    text_columns = cast(Any, {column: {"data_type": "text"} for column in spec.columns.values()})

    @dlt.resource(
        name=spec.table,
        write_disposition="merge",
        primary_key=list(spec.primary_key),
        columns=text_columns,
    )
    def resource() -> Iterator[dict[str, str]]:
        yield from _rows(zip_path, spec)

    return resource


@dlt.source(name=PIPELINE_NAME)
def kbo_source(zip_path: Path | str) -> list[Any]:
    """One dlt resource per allowlisted file in the extract."""
    path = Path(zip_path)
    if not path.exists():
        raise ExtractError(f"{path} does not exist.")
    return [_make_resource(path, spec) for spec in KBO_FILES]


def snapshot_date(zip_path: Path | str) -> date:
    """The extract's snapshot date, read from meta.csv without loading anything.

    The Makefile and the published Flight need it for the attribution line, which has to
    name the extract date, and they need it before there is a warehouse to ask.
    """
    with _reader(Path(zip_path), META_FILE) as reader:
        for row in reader:
            if row.get("Variable") != SNAPSHOT_DATE_VARIABLE:
                continue
            raw = (row.get("Value") or "").strip()
            try:
                return datetime.strptime(raw, KBO_DATE_FORMAT).date()
            except ValueError as exc:
                raise ExtractError(
                    f"{META_FILE}: {SNAPSHOT_DATE_VARIABLE} is {raw!r}, "
                    f"which is not a day-first {KBO_DATE_FORMAT} date."
                ) from exc
    raise ExtractError(f"{META_FILE} has no {SNAPSHOT_DATE_VARIABLE} row.")


def build_pipeline(destination: Any, pipelines_dir: Path | str | None = None) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=destination,
        dataset_name=DATASET_NAME,
        pipelines_dir=str(pipelines_dir or DEFAULT_PIPELINES_DIR),
    )


def run(settings: Settings, pipelines_dir: Path | str | None = None) -> LoadInfo:
    """Load the configured extract. Raises if any job failed -- a partial load is worse."""
    zip_path = settings.require_zip()
    pipeline = build_pipeline(dlt_destination(settings), pipelines_dir)
    info = pipeline.run(kbo_source(zip_path))
    info.raise_on_failed_jobs()
    return info
