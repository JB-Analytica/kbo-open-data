# Pinned versions, and why

House convention: record every pin that sits below the latest stable release, why it is
pinned there, and the one-line command that trials the newer version. A pin that is not
listed here is assumed to already track the latest stable release.

Current resolved versions (from `uv.lock` in the repo root -- re-check with
`grep -A1 '^name = "<pkg>"' uv.lock` rather than reading the whole lockfile):

| Package      | Resolved  | Where             |
|--------------|-----------|-------------------|
| `dbt-core`   | `1.12.5`  | `pyproject.toml` (`>=1.9,<2`) |
| `dbt-duckdb` | `1.11.0`  | `pyproject.toml` (`>=1.9`)    |
| `duckdb`     | `1.5.5`   | `pyproject.toml` (`>=1.1`), locally |
| `dlt`        | `1.30.0`  | `pyproject.toml` (`>=1.10`)   |
| `paramiko`   | `5.0.0`   | `pyproject.toml` `sftp` extra (`>=3.5`) |

## `dbt-core<2`

`pyproject.toml` caps `dbt-core` at `<2` because `dbt-duckdb` has no dbt 2.0-compatible
release yet. This is an upstream compatibility constraint, not a preference for the 1.x
line -- lifting it before `dbt-duckdb` supports dbt 2.0 would just break the adapter.

Trial the newer 1.x line (this does not touch the `<2` cap, since dbt 2.0 is not
adapter-compatible yet):

```
uv sync --upgrade-package dbt-core --upgrade-package dbt-duckdb
```

Watch for: a `dbt-duckdb` release that supports dbt 2.0. Once one ships, lift the cap in
`pyproject.toml` and re-pin both packages together -- an adapter and dbt-core version
mismatch fails at runtime, not at install time.

## `flight/requirements.txt`: `duckdb==1.5.5`

This is a runtime constraint, not a preference: MotherDuck's Flight runtime currently
accepts `duckdb==1.5.5`, and an unpinned install there can resolve to a `duckdb` release
MotherDuck does not accept, which fails the Flight rather than the local environment.

This pin can lag the `duckdb` version the repo resolves locally (`pyproject.toml` only
requires `>=1.1`, and `uv.lock` above happens to also resolve `1.5.5` today, coincidence
aside). That is fine by design -- the local/CI environment and the Flight container are
separate, and nothing requires them to move in lockstep. The Flight's `duckdb` pin
should track whatever version MotherDuck's runtime documentation says it accepts, not
whatever `uv.lock` resolves to at the time.

Check MotherDuck's current supported `duckdb` version before bumping this pin; there is
no local command that trials it; a bumped pin has to be verified against an actual
Flight run.

## Everything else

`dlt`, `dbt-duckdb`, `paramiko`, `python-dotenv`, `typer`, and `pyarrow` are all
range-pinned in `pyproject.toml` (`>=`) with no upper bound, so `uv lock --upgrade`
already tracks their latest stable releases. Re-resolve and re-check the pins recorded
in `flight/requirements.txt` after any such upgrade:

```
uv lock --upgrade
```
