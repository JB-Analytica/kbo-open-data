"""The KBO extract, read out of the downloaded zip and loaded into DuckDB with dlt.

The one thing to understand here is `KBO_FILES`. KBO ships natural persons (sole traders)
whose name, street and e-mail address are personal data. This module therefore reads a
**column-level allowlist**: only the files listed below are opened, and only the columns
listed on each of them are ever pulled out of the archive. `denomination.csv` (company and
person names) and `contact.csv` (e-mail, phone, web) are absent on purpose -- nothing
downstream needs them, so they are never opened at all. Everything else about this module
is plumbing; the table below is the privacy claim.

The allowlist is enforced by `pyarrow.csv`'s `include_columns`, which projects at parse
time: a column outside it is never decoded, let alone turned into a Python object.

Every column lands as TEXT. KBO writes dates day-first (`31-12-2026`), and letting dlt
infer a type turns that into either a wrong date or a failed load. dbt casts in staging.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import IO, Any, cast

import dlt
import pyarrow as pa
import pyarrow.csv as pacsv
from dlt.common.pipeline import LoadInfo

from ingest.config import Settings, dlt_destination

# The pyarrow/parquet path does not add lineage columns unless asked, and dbt source
# freshness reads `_dlt_load_id`. Set it here rather than in .dlt/config.toml so the
# setting travels with the code and applies from any working directory, tests included.
os.environ.setdefault("NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_LOAD_ID", "true")
os.environ.setdefault("NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_ID", "true")

logger = logging.getLogger(__name__)

PIPELINE_NAME = "kbo"
DATASET_NAME = "kbo_raw"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PIPELINES_DIR = REPO_ROOT / ".dlt" / "pipelines"

META_FILE = "meta.csv"
SNAPSHOT_DATE_VARIABLE = "SnapshotDate"
EXTRACT_TYPE_VARIABLE = "ExtractType"
FULL_EXTRACT_TYPE = "full"
KBO_DATE_FORMAT = "%d-%m-%Y"

# Parquet, so DuckDB bulk-reads the load package instead of replaying 41M INSERTs.
LOADER_FILE_FORMAT = "parquet"

# One CSV block per Arrow batch. Peak memory scales with this and read throughput does
# not: measured on activity.csv, 64 MiB blocks cost 3.1 GB of RSS and 4 MiB cost 0.4 GB,
# both at ~4 s. Batches are still thousands of rows, which is the point -- 34M rows cross
# the Python boundary a few hundred times instead of 34 million.
CSV_BLOCK_SIZE = 4 << 20


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
    # KBO restates this file in full in every extract, update files included, so merging
    # it would only let a retired row survive its own removal.
    always_full: bool = False

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
        always_full=True,
    ),
    KboFile(
        filename="code.csv",
        table="code",
        source_columns=("Category", "Code", "Language", "Description"),
        primary_key=("category", "code", "language"),
        always_full=True,
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
def _member(zip_path: Path, filename: str) -> Iterator[IO[bytes]]:
    """Open one member of the zip as a byte stream.

    A real extract is gigabytes, so this never materialises a file: `zipfile.open` gives
    a stream and both readers below consume it incrementally.
    """
    with zipfile.ZipFile(zip_path) as archive:
        try:
            handle = archive.open(filename)
        except KeyError as exc:
            raise ExtractError(
                f"{filename} is missing from {zip_path}. Is this a KBO Open Data zip?"
            ) from exc
        with handle:
            yield handle


@contextmanager
def _reader(zip_path: Path, filename: str) -> Iterator[csv.DictReader]:
    """Open one member of the zip as a csv.DictReader.

    Only the six-row `meta.csv` is read this way -- the bulk files go through pyarrow --
    because meta is consulted before there is a pipeline and row-at-a-time reads clearer.
    `utf-8-sig`, because KBO leads some files with a BOM.
    """
    with (
        _member(zip_path, filename) as handle,
        io.TextIOWrapper(handle, encoding="utf-8-sig", newline="") as text,
    ):
        yield csv.DictReader(text)


def _header(zip_path: Path, filename: str) -> list[str]:
    """The file's header names, read without parsing the body.

    pyarrow's own complaint about an `include_columns` entry names one column and not the
    file's actual contents, which is no help when KBO changes a layout. Reading the header
    first keeps the existing, specific `ExtractError`.
    """
    with _member(zip_path, filename) as handle:
        head = handle.read(1 << 16)
    first_line = head.decode("utf-8-sig", errors="replace").splitlines()[:1]
    return next(csv.reader(first_line), [])


def _require_columns(spec: KboFile, header: Sequence[str] | None) -> None:
    present = set(header or ())
    missing = [column for column in spec.source_columns if column not in present]
    if missing:
        raise ExtractError(
            f"{spec.filename} is missing required column(s) {', '.join(missing)}. "
            f"Found: {', '.join(sorted(present)) or '(no header)'}. "
            "The KBO layout changed, or this is not a KBO extract."
        )


def _convert_options(spec: KboFile) -> pacsv.ConvertOptions:
    return pacsv.ConvertOptions(
        # The allowlist as a parse-time projection: nothing else is even decoded.
        include_columns=list(spec.source_columns),
        # Typing is dbt's job; inference over a day-first date is the classic bite.
        column_types=dict.fromkeys(spec.source_columns, pa.string()),
        # KBO writes an absent value as `""`, and staging compares against '' not NULL.
        strings_can_be_null=False,
    )


def _landed_schema(spec: KboFile) -> pa.Schema:
    """Every column a string under its landed name, key columns marked non-nullable so the
    Arrow schema agrees with the primary key dlt derives from the same tuple."""
    return pa.schema(
        [
            pa.field(_snake(source), pa.string(), nullable=_snake(source) not in spec.primary_key)
            for source in spec.source_columns
        ]
    )


def _batches(zip_path: Path, spec: KboFile) -> Iterator[pa.RecordBatch]:
    """Yield Arrow batches of the allowlisted columns, under their landed names."""
    _require_columns(spec, _header(zip_path, spec.filename))
    schema = _landed_schema(spec)
    with _member(zip_path, spec.filename) as handle:
        try:
            batches = pacsv.open_csv(
                handle,
                read_options=pacsv.ReadOptions(block_size=CSV_BLOCK_SIZE),
                # A quoted field may contain a line break -- a street name in address.csv
                # does -- and pyarrow would otherwise split the row at it. `csv` handled
                # this for free; here it has to be asked for.
                parse_options=pacsv.ParseOptions(newlines_in_values=True),
                convert_options=_convert_options(spec),
            )
            for batch in batches:
                # Selected by name rather than trusting the batch's order: the allowlist
                # decides what leaves this function, a second time and for free.
                columns = [batch.column(source) for source in spec.source_columns]
                yield pa.RecordBatch.from_arrays(columns, schema=schema)
        except pa.ArrowKeyError as exc:
            raise ExtractError(
                f"{spec.filename}: {exc}. The KBO layout changed, or this is not a KBO extract."
            ) from exc


def _rows(zip_path: Path, spec: KboFile) -> Iterator[dict[str, str]]:
    """Row-wise view of `_batches`, so the allowlist can be inspected without a warehouse.

    The load path yields the batches themselves: turning 34M rows into dicts is precisely
    the cost this module is shaped to avoid.
    """
    for batch in _batches(zip_path, spec):
        yield from batch.to_pylist()


def _make_resource(zip_path: Path, spec: KboFile, write_disposition: str) -> Any:
    text_columns = cast(Any, {column: {"data_type": "text"} for column in spec.columns.values()})

    @dlt.resource(
        name=spec.table,
        write_disposition=cast(Any, write_disposition),
        primary_key=list(spec.primary_key),
        columns=text_columns,
        file_format=cast(Any, LOADER_FILE_FORMAT),
    )
    def resource() -> Iterator[pa.RecordBatch]:
        yield from _batches(zip_path, spec)

    return resource


def _meta_value(zip_path: Path, variable: str) -> str | None:
    with _reader(zip_path, META_FILE) as reader:
        for row in reader:
            if row.get("Variable") == variable:
                return (row.get("Value") or "").strip()
    return None


def extract_type(zip_path: Path | str) -> str:
    """`meta.csv`'s ExtractType: `full` for a complete restatement, otherwise an update."""
    value = _meta_value(Path(zip_path), EXTRACT_TYPE_VARIABLE)
    if not value:
        raise ExtractError(
            f"{META_FILE} has no {EXTRACT_TYPE_VARIABLE} row, so there is no way to tell a "
            "full extract from an update file. Is this a KBO Open Data zip?"
        )
    return value.lower()


def _write_disposition(spec: KboFile, is_full_extract: bool) -> str:
    """A full extract restates every row, so `replace` is both correct and far cheaper:
    `merge` stages a second copy of all 41M rows to reach the same result. An update file
    carries only what changed, so it has to merge on the primary key.
    """
    return "replace" if is_full_extract or spec.always_full else "merge"


@dlt.source(name=PIPELINE_NAME)
def kbo_source(zip_path: Path | str) -> list[Any]:
    """One dlt resource per allowlisted file in the extract."""
    path = Path(zip_path)
    if not path.exists():
        raise ExtractError(f"{path} does not exist.")
    kind = extract_type(path)
    is_full = kind == FULL_EXTRACT_TYPE
    dispositions = {spec.table: _write_disposition(spec, is_full) for spec in KBO_FILES}
    # Switching between replace and merge without saying so would be a nasty surprise.
    logger.info(
        "%s: %s=%r, treated as %s; write disposition %s",
        path.name,
        EXTRACT_TYPE_VARIABLE,
        kind,
        "a full restatement" if is_full else "an update file",
        ", ".join(f"{table}={mode}" for table, mode in sorted(dispositions.items())),
    )
    return [_make_resource(path, spec, dispositions[spec.table]) for spec in KBO_FILES]


def snapshot_date(zip_path: Path | str) -> date:
    """The extract's snapshot date, read from meta.csv without loading anything.

    The Makefile and the published Flight need it for the attribution line, which has to
    name the extract date, and they need it before there is a warehouse to ask.
    """
    raw = _meta_value(Path(zip_path), SNAPSHOT_DATE_VARIABLE)
    if raw is None:
        raise ExtractError(f"{META_FILE} has no {SNAPSHOT_DATE_VARIABLE} row.")
    try:
        return datetime.strptime(raw, KBO_DATE_FORMAT).date()
    except ValueError as exc:
        raise ExtractError(
            f"{META_FILE}: {SNAPSHOT_DATE_VARIABLE} is {raw!r}, "
            f"which is not a day-first {KBO_DATE_FORMAT} date."
        ) from exc


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
