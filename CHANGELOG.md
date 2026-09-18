# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- First cut of the pipeline: dlt extract from a local KBO zip, dbt staging and five
  aggregate marts on DuckDB, with MotherDuck as a one-variable deploy target.
- Natural-person entities excluded at the model level, derived from `code.csv` rather than
  hardcoded, with dbt tests guarding both the exclusion and the code's continued existence.
- Small-cell suppression (fewer than 5 entities) before anything is published.
- Aggregate marts committed as Parquet under `data/published/`.

### Fixed

- First run against a real extract (2026-09-17) corrected three assumptions the synthetic
  fixture had baked in: `code.csv` carries NL, FR and DE and no English at all; the
  registered-office address type is described as `Zetel`, not `Maatschappelijke zetel`; and
  `TypeOfEnterprise` defines an `Onbekend` code. The fixture now mirrors the real code table,
  so the same class of error cannot pass `make demo` again.
- The entity-type filter is an allowlist (keep only `Rechtspersoon`) rather than a denylist,
  so an unrecognised entity type can never be admitted by default.
- `make demo` uses its own warehouse file. It previously shared `DUCKDB_PATH` with a real
  run and would have merged synthetic rows into a real extract's tables.
