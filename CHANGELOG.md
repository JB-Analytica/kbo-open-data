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
