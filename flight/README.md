# The `kbo-open-data-refresh` Flight

## What a Flight actually is

MotherDuck's current documentation is explicit: a Flight is not a directory you upload.
It is a definition MotherDuck holds -- a name, Python `source_code`, an optional
`requirements_txt`, an optional non-secret `config` map, optional `flight_secret_names`,
an optional `access_token_name`, an optional five-field **UTC** `schedule_cron`, and an
optional `max_runtime_sec` -- created and updated through the MotherDuck API or MCP
tools. Each run installs `requirements.txt` once, then executes `main.py` as
`python main.py`.

The files in this directory are the version-controlled source of truth for that
definition, reviewed in a pull request like any other code change. They are not a
deployable bundle MotherDuck reads off disk. Publishing means pushing their contents
into a Flight definition through the API or MCP tools -- see the field mapping below.

## What it does

**The raw layer never leaves the container.** The Flight loads the extract into a DuckDB
file under `/tmp` -- the container has 150 GB of scratch there -- builds the marts against
that same file, and copies only the five aggregate marts (276 rows, about 20 KB as
Parquet) into MotherDuck. The 41 million raw rows, 770,434 of them natural persons, are deleted with the
rest of the staging directory when the run ends. There is no code path from `kbo_raw` to
MotherDuck, which also keeps the published database well inside a 10 GB free tier.

On each run, `main.py`:

1. Reads its non-secret configuration from the environment (`config`, below).
2. Fetches the KBO daily update file over SFTP, using the `flight_secret_names` below.
   Fails with a clear message, not a traceback, if those secrets are not set (see the
   SFTP caveat below).
3. Stages the file under `/tmp/`.
4. Clones the public repo (`KBO_FLIGHT_REPO_URL`, MIT, public) at `KBO_FLIGHT_REPO_REF`
   into `/tmp/`, since the Flight container does not carry this repo's `ingest/` and
   `transform/` on its own.
5. Runs the dlt load into `/tmp/<staging>/kbo.duckdb`, then `dbt build --project-dir
   transform --profiles-dir transform` against that same file, then the `export_marts`
   run-operation. All local; no credentials are involved up to this point.
6. Runs `kbo publish`, which copies the `marts` schema -- and nothing else -- into the
   MotherDuck database named by `MOTHERDUCK_DATABASE`, creating it if it does not exist.
   `MOTHERDUCK_TOKEN` is injected by the runtime from `access_token_name` and reaches
   DuckDB through the environment, never through a connection string that could be echoed
   into a log.
7. Verifies the result **in MotherDuck** -- row counts and the snapshot date landed in
   each of the five marts, and that all five agree on the same snapshot date -- rather
   than trusting a zero exit code. MotherDuck is what the Dive and the share read, so
   that is what gets checked. A verification failure fails the run.
8. Cleans up everything it staged under `/tmp/`, including the raw warehouse, because the
   container can be reused between runs.

It logs what it did at each step. It never logs a secret value.

## Publishing this definition

Publish through the MotherDuck API or MCP tools, not by uploading this directory. The
field-to-file mapping:

| Flight field         | Source in this directory                                    |
|-----------------------|--------------------------------------------------------------|
| `name`                | `flight.metadata.json` -> `name`                             |
| `source_code`         | `main.py`, read as a string                                  |
| `requirements_txt`    | `requirements.txt`, read as a string                         |
| `config`              | `flight.metadata.json` -> `config`                            |
| `flight_secret_names` | `flight.metadata.json` -> `flight_secret_names`               |
| `access_token_name`   | `flight.metadata.json` -> `access_token_name`                 |
| `schedule_cron`       | `flight.metadata.json` -> `schedule_cron` (see the cron caveat below -- currently left unset) |
| `max_runtime_sec`     | `flight.metadata.json` -> `max_runtime_sec`                   |

Re-publish after any change to `main.py` or `requirements.txt` by updating the same
Flight definition; do not create a second Flight for the same job.

## Secrets

`flight.metadata.json` declares three secret names, matching the namespaced form
`main.py` reads first (`kbo_sftp_<KEY>`, falling back to the raw alias for local testing):

- `kbo_sftp_KBO_SFTP_HOST`
- `kbo_sftp_KBO_SFTP_USER`
- `kbo_sftp_KBO_SFTP_PASSWORD`

Create these in the MotherDuck UI, not by passing values through a chat message or a
command line -- that is the whole point of a Flight secret. `access_token_name` should
point at a **service-account token**, not a personal one: a Flight runs unattended on a
schedule (once one exists) and outlives whoever set it up, so it must not be tied to one
person's MotherDuck login.

## The SFTP caveat

SFTP access to the KBO daily update file must be requested from
**kbo-bce-webservice@economie.fgov.be** and, as of writing, may not have been granted.

If it has not been granted:

- Do not set the `kbo_sftp_*` secrets. `main.py` checks for them before doing anything
  else and exits with a clear, actionable message (not a traceback) when they are
  missing.
- Refresh the warehouse manually instead -- download the extract from the KBO web
  portal and run `kbo load` locally, or from the repo's own CI/Makefile path.
- Create this Flight without a schedule and run it on demand only, once SFTP access is
  granted, to confirm the end-to-end path works before trusting it to a cron.

## The cron caveat

The KBO daily file's exact publication time is **not confirmed**.
`flight.metadata.json` currently leaves `schedule_cron` unset, so the Flight is
on-demand only.

Once the publication time is confirmed, the intended schedule is:

```
0 5 * * *
```

(05:00 UTC daily -- a placeholder guess, not a confirmed publication time.) Do not set
`schedule_cron` to this or any other value until that hour has been checked against the
actual publication time on the SFTP drop. `schedule_cron` is five fields, evaluated in
**UTC**.

## Running on demand and reading logs

Run the Flight on demand and read its logs through the same MotherDuck API/MCP tools
used to publish it (`run_flight` / `get_flight_run` / `get_flight_logs`, or their UI
equivalents) rather than by running `main.py` directly against production -- on-demand
runs use the same definition and secrets as a scheduled run would.
