"""Settings for the extract-and-load layer, read from the environment.

Everything is configuration rather than an argument because the same code runs from a
laptop, a Makefile and a MotherDuck Flight, and only the Flight has credentials.

`DESTINATION` names where the *published marts* go, not where the pipeline runs. The
load and the dbt build always run against a local DuckDB file, so the raw layer -- and
the natural persons in it -- never leaves the machine that loaded it. See
`ingest/publish.py`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:  # pragma: no cover - typing only
    from dlt.common.destination import Destination

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where `kbo publish` sends the marts. `duckdb` means "nowhere, they stay local".
DESTINATIONS = ("duckdb", "motherduck")


class ConfigError(RuntimeError):
    """Configuration is missing or inconsistent. Always carries the fix in its message."""


@dataclass(frozen=True)
class Settings:
    kbo_zip: Path | None = None
    destination: str = "duckdb"
    duckdb_path: Path = Path("kbo.duckdb")
    motherduck_token: str | None = None
    motherduck_database: str = "kbo"
    sftp_host: str | None = None
    sftp_user: str | None = None
    sftp_password: str | None = None
    sftp_dir: str | None = None

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        load_dotenv(env_file or REPO_ROOT / ".env")
        destination = (os.getenv("DESTINATION") or "duckdb").strip().lower()
        if destination not in DESTINATIONS:
            raise ConfigError(
                f"DESTINATION={destination!r} is not supported. "
                f"Use one of: {', '.join(DESTINATIONS)}."
            )
        zip_path = os.getenv("KBO_ZIP")
        return cls(
            kbo_zip=Path(zip_path) if zip_path else None,
            destination=destination,
            duckdb_path=Path(os.getenv("DUCKDB_PATH") or "kbo.duckdb"),
            motherduck_token=os.getenv("MOTHERDUCK_TOKEN") or None,
            motherduck_database=os.getenv("MOTHERDUCK_DATABASE") or "kbo",
            sftp_host=os.getenv("KBO_SFTP_HOST") or None,
            sftp_user=os.getenv("KBO_SFTP_USER") or None,
            sftp_password=os.getenv("KBO_SFTP_PASSWORD") or None,
            sftp_dir=os.getenv("KBO_SFTP_DIR") or None,
        )

    @property
    def publishes_to_motherduck(self) -> bool:
        """Whether a build should be followed by a publish to MotherDuck."""
        return self.destination == "motherduck"

    def require_zip(self) -> Path:
        if self.kbo_zip is None:
            raise ConfigError(
                "KBO_ZIP is not set. Point it at the extract you downloaded from "
                "https://kbopub.economie.fgov.be/kbo-open-data, or run "
                "`kbo demo-extract` to write a synthetic one."
            )
        if not self.kbo_zip.exists():
            raise ConfigError(f"KBO_ZIP points at {self.kbo_zip}, which does not exist.")
        return self.kbo_zip


def dlt_destination(settings: Settings) -> Destination:
    """Return the dlt destination for the load: always the local DuckDB file.

    There is deliberately no destination switch here. The raw layer holds 770,434 natural
    persons, whose non-publication is the premise of this project, so it is loaded locally
    and published from there -- `DESTINATION=motherduck` adds a publish step, it does not
    move the pipeline. A cloud destination cannot be reached from this function at all,
    which is a stronger guarantee than a filter would be.
    """
    import dlt

    return dlt.destinations.duckdb(str(settings.duckdb_path))
