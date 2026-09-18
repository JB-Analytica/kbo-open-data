"""Copy the aggregate marts out of the local warehouse into a published database.

This is the only step that talks to a cloud account, and it moves the marts and nothing
else. The raw layer -- 41 million rows, including 770,434 natural persons -- is loaded
into a local DuckDB file and stays on the machine that loaded it. There is no code path
from `kbo_raw` to MotherDuck, which is a stronger guarantee than a filter would be.

The target is a parameter rather than a constant, so the publish path is exercised by
tests against a second local DuckDB file, with no account, credentials or network.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ingest.config import ConfigError, Settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from duckdb import DuckDBPyConnection

log = logging.getLogger(__name__)

MARTS_SCHEMA = "marts"
MOTHERDUCK_PREFIX = "md:"
#: Catalog alias for a local target. Fixed, so nothing depends on the target file's name.
LOCAL_ALIAS = "publish_target"
SOURCE_ALIAS = "local_warehouse"


class PublishError(RuntimeError):
    """Publishing cannot proceed. Always carries the fix in its message."""


@dataclass(frozen=True)
class PublishTarget:
    """Where the marts go: a MotherDuck database, or a second local DuckDB file."""

    attach_spec: str
    database: str
    is_motherduck: bool

    @classmethod
    def motherduck(cls, database: str) -> PublishTarget:
        return cls(attach_spec=MOTHERDUCK_PREFIX, database=database, is_motherduck=True)

    @classmethod
    def local(cls, path: Path | str) -> PublishTarget:
        return cls(attach_spec=str(path), database=LOCAL_ALIAS, is_motherduck=False)

    @classmethod
    def parse(cls, spec: str) -> PublishTarget:
        """`md:<database>` is MotherDuck; anything else is a path to a DuckDB file."""
        if spec.startswith(MOTHERDUCK_PREFIX):
            database = spec[len(MOTHERDUCK_PREFIX) :].strip()
            if not database:
                raise PublishError(
                    "A MotherDuck target needs a database name: use md:<database>, "
                    "for example md:kbo."
                )
            return cls.motherduck(database)
        return cls.local(spec)

    def __str__(self) -> str:
        return f"{MOTHERDUCK_PREFIX}{self.database}" if self.is_motherduck else self.attach_spec


@dataclass(frozen=True)
class PublishedMart:
    """One mart that arrived, and how many rows arrived with it."""

    name: str
    row_count: int


def motherduck_target(settings: Settings) -> PublishTarget:
    """The MotherDuck target for these settings, or a ConfigError saying what is missing.

    MotherDuck has no anonymous mode and no database name that is safe to guess. Without
    an explicit token DuckDB would reach for whatever token is in the ambient environment,
    which is how a publish ends up in somebody else's account. Refuse instead.
    """
    if not settings.motherduck_token:
        raise ConfigError(
            "Publishing to MotherDuck needs MOTHERDUCK_TOKEN. Set it to a service-account "
            "token (a Flight injects one automatically), or publish to a local DuckDB file "
            "with `kbo publish --to <path>`."
        )
    return PublishTarget.motherduck(settings.motherduck_database)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def publish_marts(
    source_path: Path | str,
    target: PublishTarget,
    *,
    motherduck_token: str | None = None,
    schema: str = MARTS_SCHEMA,
) -> list[PublishedMart]:
    """Replace every mart in `target` with the one of the same name in `source_path`.

    The mart list is read from the source warehouse rather than hardcoded: dbt decides
    what a mart is, and a sixth one must not need an edit here. Returns what was written,
    so the caller can log and verify rather than trust a silent success.
    """
    import duckdb

    source = Path(source_path)
    if not source.exists():
        raise PublishError(
            f"There is no warehouse at {source}. Run the build first (`make build`), or "
            "point --from at the DuckDB file that holds the marts."
        )

    if target.is_motherduck and motherduck_token:
        # The token goes through the environment, never into a connection string: DuckDB
        # echoes connection strings into its error messages, and a Flight's logs are
        # readable by anyone who can see the Flight.
        os.environ.setdefault("MOTHERDUCK_TOKEN", motherduck_token)

    # An in-memory connection attaches both sides: the source read-only -- nothing here
    # may ever write to the warehouse -- and the target read-write. Opening the source
    # itself read-only would force the attached target read-only with it.
    connection = duckdb.connect()
    try:
        connection.execute(f"ATTACH {_literal(str(source))} AS {_quote(SOURCE_ALIAS)} (READ_ONLY)")
        marts = _source_marts(connection, schema)
        if not marts:
            raise PublishError(
                f"The `{schema}` schema in {source} is missing or empty, so there is nothing "
                "to publish. Run the build first (`make build`)."
            )

        _attach_target(connection, target)
        connection.execute(
            f"CREATE SCHEMA IF NOT EXISTS {_quote(target.database)}.{_quote(schema)}"
        )

        published: list[PublishedMart] = []
        for mart in marts:
            destination = f"{_quote(target.database)}.{_quote(schema)}.{_quote(mart)}"
            origin = f"{_quote(SOURCE_ALIAS)}.{_quote(schema)}.{_quote(mart)}"
            connection.execute(f"CREATE OR REPLACE TABLE {destination} AS SELECT * FROM {origin}")
            row = connection.execute(f"SELECT COUNT(*) FROM {destination}").fetchone()
            row_count = int(row[0]) if row else 0
            log.info("published %s -- %s rows -> %s", mart, row_count, target)
            published.append(PublishedMart(name=mart, row_count=row_count))
        return published
    finally:
        connection.close()


def _source_marts(connection: DuckDBPyConnection, schema: str) -> list[str]:
    """Every table in the source warehouse's mart schema, in a stable order.

    Read from the catalog, never hardcoded: a mart added to dbt is published by the next
    run without a second edit here.
    """
    rows = connection.execute(
        "SELECT table_name FROM duckdb_tables() "
        "WHERE database_name = ? AND schema_name = ? ORDER BY table_name",
        [SOURCE_ALIAS, schema],
    ).fetchall()
    return [str(name) for (name,) in rows]


def _attach_target(connection: DuckDBPyConnection, target: PublishTarget) -> None:
    if not target.is_motherduck:
        connection.execute(f"ATTACH {_literal(target.attach_spec)} AS {_quote(target.database)}")
        return
    # `md:` on its own attaches the account's catalog. The database is then created if
    # needed, because a fresh connection may not carry it and the failure is an unhelpful
    # `Catalog Error: Catalog with name "<db>" does not exist`.
    connection.execute(f"ATTACH {_literal(MOTHERDUCK_PREFIX)}")
    connection.execute(f"CREATE DATABASE IF NOT EXISTS {_quote(target.database)}")
