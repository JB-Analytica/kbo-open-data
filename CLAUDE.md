# kbo-open-data

An open-source pipeline that turns the Belgian company register (KBO Open Data, FOD
Economie) into five published aggregate tables and a MotherDuck Dive. Public, MIT, and the
shop window for JB Analytica's stack — so the repo itself is part of the deliverable.

## Commands

```bash
uv sync --extra dev
make demo                        # whole pipeline on a synthetic extract: no zip, no account
make build                       # the real thing, from the zip named by KBO_ZIP in .env
make test                        # uv run poe check -- ruff + ty + pytest
uv run dbt build --project-dir transform --profiles-dir transform
```

`make demo` is the fast loop. It is also what CI runs, because the repo's central promise is
that a clean clone works with no credentials.

## Layout

- `ingest/` — the dlt source. Reads a KBO zip through a **column-level allowlist**; see below.
- `transform/` — the dbt project. `models/staging`, `models/intermediate`, `models/marts`,
  plus the seeds that map postcodes to provinces and NACE divisions to sections.
- `flight/` — version-controlled source for the MotherDuck Flight that refreshes daily.
  Not a deployable directory: a Flight is a definition held by MotherDuck, published from
  these files through its API.
- `dive/` — how the published Dive is built and shared. Documentation only.
- `data/raw/` — git-ignored. `data/published/` — the aggregate Parquet, committed.
- `tests/fixtures/synthetic_kbo.py` — the fake extract everything is verified against.

## How to work

The main session plans, briefs, reviews and integrates; self-contained implementation,
broad searches and doc passes go to subagents on cheaper models (see the jba-core
`delegating-implementation` skill). Small edits are done directly. Keep this section as is —
it is the only copy of the rule a cloud session sees.

## Conventions specific to this repo

- **Privacy is the design, not a filter.** Three layers, and a change may not weaken any of
  them without saying so out loud:
  1. `denomination.csv` and `contact.csv` are never opened, and `ingest/` reads only an
     explicit allowlist of columns out of the files it does open. No name, street or contact
     detail ever enters the warehouse.
  2. Natural-person entities are excluded at the **model** level, in
     `int_active_enterprise`, so they cannot reach a mart.
  3. Aggregate cells below `var('min_cell_size')` (5) are suppressed before publishing.
- **Never hardcode a KBO code value.** `TypeOfEnterprise`, `Status`, `JuridicalForm`,
  `Classification` and `TypeOfAddress` are coded and `code.csv` is the only authority.
  `int_code_resolution` resolves each concept the project depends on by *description*, and
  `assert_expected_codes_resolve.sql` fails the build if a future extract drops one. That
  test is the safety net for the whole privacy design — do not weaken it.
- **Attribution is a licence obligation**, not a courtesy (KBO gebruiksvoorwaarden art. 2.8).
  Every mart carries `snapshot_date`, taken from `meta.csv` — the date of the *data update*,
  never the date the job ran.
- **Model naming deviates from house style on purpose.** `stg_*` without the source infix and
  `agg_*` instead of `dim_`/`fct_`, because this is a single-source public repo where the
  names are read by strangers. dbt-preflight's `jba` preset would flag it, which is why
  preflight is not wired into this repo.
- One dbt project, one profile, two targets. `DESTINATION=motherduck` is the only difference
  between local and deployed; a model that knows which destination it is on is a bug.

## Gotchas

- **KBO dates are day-first (`DD-MM-YYYY`).** Everything is loaded as TEXT and parsed in
  staging, deliberately, so type inference cannot read `03-04-2024` as 4 March.
- **`activity.csv` carries several NACE versions.** Filter to one explicitly (`var('nace_version')`)
  or every sector count is silently inflated.
- **dbt's working directory is `transform/`**, so a relative `DUCKDB_PATH` lands in the wrong
  place. The Makefile exports an absolute path; `profiles.yml` defaults to `../kbo.duckdb`
  for anyone running dbt by hand.
- **The KBO cookbook and licence PDFs say the extract is monthly. They are stale** — a full
  file and an update file are published daily and kept for 31 days. Build against the daily
  files.
- There is **no anonymous download**. Registration at
  `kbopub.economie.fgov.be/kbo-open-data` is required, and the zip is placed in `data/raw/`
  by hand. Nothing in this repo may try to scrape the portal.
- The Flight needs SFTP access that FOD Economie grants on request
  (`kbo-bce-webservice@economie.fgov.be`). Until it is granted, the refresh is manual and the
  Flight stays on-demand.
