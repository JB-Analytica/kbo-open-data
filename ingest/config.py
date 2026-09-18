"""Settings for the extract-and-load layer, read from the environment.

Everything is configuration rather than an argument because the same code runs from a
laptop, a Makefile and a MotherDuck Flight, and only the Flight has credentials.
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
    """Return the dlt destination for the configured DESTINATION.

    MotherDuck has no anonymous mode and no database name that is safe to guess. Without
    an explicit token dlt would reach for whatever token is in the ambient environment,
    which is how a load ends up in somebody else's account. Refuse instead.
    """
    import dlt

    if settings.destination == "motherduck":
        if not settings.motherduck_token:
            raise ConfigError(
                "DESTINATION=motherduck needs MOTHERDUCK_TOKEN. Set it to a service-account "
                "token (a Flight injects one automatically), or use DESTINATION=duckdb."
            )
        # The token goes through the environment, not into the connection string: dlt and
        # DuckDB both echo a connection string into logs on failure, and a Flight's logs
        # are readable by anyone who can see the Flight.
        os.environ.setdefault("MOTHERDUCK_TOKEN", settings.motherduck_token)
        return dlt.destinations.motherduck(credentials=f"md:{settings.motherduck_database}")
    return dlt.destinations.duckdb(str(settings.duckdb_path))
