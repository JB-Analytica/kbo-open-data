"""Entry point for the `kbo-open-data-refresh` MotherDuck Flight.

A Flight is not a directory you upload -- it is a definition MotherDuck holds (name,
source, requirements, config, secrets, schedule) created and updated through the
MotherDuck API or MCP tools, from the field-to-file mapping in flight/README.md. Each
scheduled or on-demand run installs flight/requirements.txt once, then executes this file
as `python main.py`. This file is the version-controlled source of truth for that source
code, not something the runtime reads off disk as a bundle.

The repo's own ingest/ and transform/ are not present in the Flight container, so this
script clones the public repo into /tmp at a configurable ref and runs from there. That
keeps the Flight source small (it is capped at 200 KB) and means the Flight always runs
the code that is actually on the ref it was told to use.

Deliberately does one thing: fetch the daily update, load it, build the marts, export
them, verify the result. A Flight that tries to do more is a Flight that fails in ways
nobody can debug.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

MART_NAMES = (
    "agg_enterprises_by_legal_form",
    "agg_enterprises_by_nace_section",
    "agg_enterprises_by_province",
    "agg_enterprises_by_start_year",
    "agg_establishments_per_enterprise",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kbo-flight")


class FlightError(RuntimeError):
    """A problem this Flight can explain in one line, so the log never ends in a traceback."""


@dataclass(frozen=True)
class Config:
    """Non-secret configuration, read from the Flight's `config` map (env at run time)."""

    repo_url: str
    repo_ref: str
    motherduck_database: str
    sftp_dir: str
    sftp_remote_name: str
    dbt_threads: str
    min_cell_size: str
    nace_version: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            repo_url=os.environ.get(
                "KBO_FLIGHT_REPO_URL", "https://github.com/JB-Analytica/kbo-open-data"
            ),
            repo_ref=os.environ.get("KBO_FLIGHT_REPO_REF", "main"),
            motherduck_database=os.environ.get("MOTHERDUCK_DATABASE", "kbo"),
            sftp_dir=os.environ.get("KBO_SFTP_DIR", ""),
            # PLACEHOLDER: the daily file's naming convention on the SFTP drop is not
            # confirmed. Set KBO_FLIGHT_REMOTE_NAME once SFTP access is granted and the
            # real pattern is known (see flight/README.md).
            sftp_remote_name=os.environ.get("KBO_FLIGHT_REMOTE_NAME", "KboOpenData_Update.zip"),
            # 2 CPU cores in the Flight container -- more threads just contend.
            dbt_threads=os.environ.get("KBO_DBT_THREADS", "2"),
            min_cell_size=os.environ.get("KBO_MIN_CELL_SIZE", "5"),
            nace_version=os.environ.get("KBO_NACE_VERSION", "2008"),
        )


def _secret(namespaced_key: str, raw_key: str) -> str | None:
    """Read a Flight secret, preferring the namespaced env-var form MotherDuck injects."""
    return os.environ.get(namespaced_key) or os.environ.get(raw_key)


def _require_sftp_secrets() -> tuple[str, str, str]:
    host = _secret("kbo_sftp_KBO_SFTP_HOST", "KBO_SFTP_HOST")
    user = _secret("kbo_sftp_KBO_SFTP_USER", "KBO_SFTP_USER")
    password = _secret("kbo_sftp_KBO_SFTP_PASSWORD", "KBO_SFTP_PASSWORD")
    missing = [
        name
        for name, value in (("host", host), ("user", user), ("password", password))
        if not value
    ]
    if missing:
        raise FlightError(
            "SFTP secrets are not set on this Flight: "
            f"{', '.join(missing)}. SFTP access has to be requested from "
            "kbo-bce-webservice@economie.fgov.be and may not have been granted yet -- "
            "see flight/README.md. Until it is, refresh manually and run this Flight "
            "on demand only."
        )
    assert host and user and password  # narrows for type checkers; missing already raised
    return host, user, password


def _run(args: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    log.info("running: %s", " ".join(args))
    subprocess.run(args, cwd=cwd, env=env, check=True)


def clone_repo(config: Config, staging_dir: Path) -> Path:
    """Clone the public repo at the configured ref. git is preinstalled in the runtime."""
    repo_dir = staging_dir / "repo"
    log.info("cloning %s into %s", config.repo_url, repo_dir)
    subprocess.run(["git", "clone", config.repo_url, str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", config.repo_ref], check=True)
    return repo_dir


def fetch_update_file(config: Config, staging_dir: Path) -> Path:
    """Fetch the KBO daily update file over SFTP using Flight secrets."""
    import paramiko

    host, user, password = _require_sftp_secrets()
    local_path = staging_dir / config.sftp_remote_name
    directory = config.sftp_dir.rstrip("/")
    remote_path = f"{directory}/{config.sftp_remote_name}" if directory else config.sftp_remote_name

    log.info("fetching %s from %s over SFTP", config.sftp_remote_name, host)
    with paramiko.Transport((host, 22)) as transport:
        transport.connect(username=user, password=password)
        client = paramiko.SFTPClient.from_transport(transport)
        if client is None:
            raise FlightError(f"Could not open an SFTP channel to {host}.")
        with client:
            client.get(remote_path, str(local_path))
    return local_path


def run_dlt_load(repo_dir: Path, zip_path: Path, base_env: dict[str, str]) -> None:
    env = {
        **base_env,
        "DESTINATION": "motherduck",
        "KBO_ZIP": str(zip_path),
    }
    _run(
        [sys.executable, "-m", "ingest.cli", "load", "--zip", str(zip_path)],
        cwd=repo_dir,
        env=env,
    )


def run_dbt_build(repo_dir: Path, config: Config, base_env: dict[str, str]) -> None:
    env = {
        **base_env,
        "DESTINATION": "motherduck",
        "KBO_MIN_CELL_SIZE": config.min_cell_size,
        "KBO_NACE_VERSION": config.nace_version,
    }
    _run(
        [
            "dbt",
            "build",
            "--project-dir",
            "transform",
            "--profiles-dir",
            "transform",
            "--target",
            "motherduck",
            "--threads",
            config.dbt_threads,
        ],
        cwd=repo_dir,
        env=env,
    )


def run_export_marts(repo_dir: Path, staging_dir: Path, base_env: dict[str, str]) -> None:
    # This writes Parquet inside the container's ephemeral /tmp, not to the repo's
    # data/published/ -- the Flight has no persistent filesystem of its own. It runs
    # the same run-operation the repo's Makefile uses, mainly so a broken export macro
    # fails the Flight rather than surfacing only when someone runs it by hand later.
    export_dir = staging_dir / "published"
    export_dir.mkdir(parents=True, exist_ok=True)
    env = {**base_env, "DESTINATION": "motherduck"}
    _run(
        [
            "dbt",
            "run-operation",
            "export_marts",
            "--project-dir",
            "transform",
            "--profiles-dir",
            "transform",
            "--target",
            "motherduck",
            "--args",
            f"{{output_dir: {export_dir}}}",
        ],
        cwd=repo_dir,
        env=env,
    )


def verify_published_marts(database: str) -> None:
    """Verify the marts actually landed, instead of trusting a zero exit code.

    Checks row counts and the snapshot date per mart, and that every mart agrees on the
    same snapshot date -- a partial rebuild that leaves one mart on an older snapshot is
    exactly the kind of failure a green dbt run does not surface.
    """
    import duckdb

    con = duckdb.connect("md:")
    con.execute(f'CREATE DATABASE IF NOT EXISTS "{database}"')

    snapshot_dates: set[str] = set()
    for mart in MART_NAMES:
        relation = f'"{database}".marts."{mart}"'
        row = con.execute(
            f"SELECT COUNT(*) AS row_count, MAX(snapshot_date) AS snapshot_date FROM {relation}"
        ).fetchone()
        if row is None:
            raise FlightError(f"Could not query {relation} after the build.")
        row_count, snapshot_date = row
        log.info("verify: %s -- %s rows, snapshot_date=%s", mart, row_count, snapshot_date)
        if row_count == 0:
            raise FlightError(f"{mart} has zero rows after the build.")
        if snapshot_date is None:
            raise FlightError(f"{mart} has a null snapshot_date after the build.")
        snapshot_dates.add(str(snapshot_date))

    if len(snapshot_dates) > 1:
        raise FlightError(
            f"Marts disagree on snapshot_date after the build: {sorted(snapshot_dates)}."
        )
    log.info("verify: all marts agree on snapshot_date=%s", next(iter(snapshot_dates)))


def main() -> None:
    config = Config.from_env()
    staging_dir = Path(tempfile.mkdtemp(prefix="kbo-flight-"))
    log.info("staging under %s", staging_dir)

    try:
        # Fail fast and clearly if SFTP was never granted, before cloning or loading
        # anything -- see flight/README.md for the "not yet granted" path.
        _require_sftp_secrets()

        repo_dir = clone_repo(config, staging_dir)
        zip_path = fetch_update_file(config, staging_dir)

        base_env = {**os.environ}
        run_dlt_load(repo_dir, zip_path, base_env)
        run_dbt_build(repo_dir, config, base_env)
        run_export_marts(repo_dir, staging_dir, base_env)
        verify_published_marts(config.motherduck_database)
        log.info("refresh complete")
    except subprocess.CalledProcessError as exc:
        log.error("step failed: %s (exit %s)", " ".join(exc.cmd), exc.returncode)
        sys.exit(1)
    except FlightError as exc:
        log.error(str(exc))
        sys.exit(1)
    finally:
        # The container can be reused between runs -- never leave the extract or the
        # clone behind for the next one to trip over.
        shutil.rmtree(staging_dir, ignore_errors=True)
        log.info("cleaned up %s", staging_dir)


if __name__ == "__main__":
    main()
