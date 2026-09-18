"""Optional SFTP fetch of the KBO daily update file.

FOD Economie grants SFTP access on request (kbo-bce-webservice@economie.fgov.be), so most
people running this repo do not have it. paramiko is therefore an extra and is imported
lazily: everything else works without it. There is no anonymous download from the web
portal and scraping it is out of scope -- download the zip yourself and set KBO_ZIP.
"""

from __future__ import annotations

from pathlib import Path

from ingest.config import ConfigError, Settings

DEFAULT_DESTINATION_DIR = Path("data/raw")


def fetch(
    settings: Settings,
    remote_name: str,
    destination_dir: Path | str = DEFAULT_DESTINATION_DIR,
) -> Path:
    """Download `remote_name` from the KBO SFTP drop to `destination_dir`."""
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover - depends on how the venv was synced
        raise ConfigError(
            "SFTP needs paramiko, which lives in the optional `sftp` extra. "
            "Install it with `uv sync --extra sftp`."
        ) from exc

    missing = [
        name
        for name, value in (
            ("KBO_SFTP_HOST", settings.sftp_host),
            ("KBO_SFTP_USER", settings.sftp_user),
            ("KBO_SFTP_PASSWORD", settings.sftp_password),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            f"SFTP is not configured: {', '.join(missing)} unset. Access has to be requested "
            "from kbo-bce-webservice@economie.fgov.be; without it, download the zip from the "
            "web portal yourself and set KBO_ZIP."
        )

    target_dir = Path(destination_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / remote_name
    directory = (settings.sftp_dir or "").rstrip("/")
    remote_path = f"{directory}/{remote_name}" if directory else remote_name

    with paramiko.Transport((settings.sftp_host, 22)) as transport:
        transport.connect(username=settings.sftp_user, password=settings.sftp_password)
        client = paramiko.SFTPClient.from_transport(transport)
        if client is None:  # pragma: no cover - paramiko only returns None on a dead channel
            raise ConfigError(f"Could not open an SFTP channel to {settings.sftp_host}.")
        with client:
            client.get(remote_path, str(local_path))
    return local_path
