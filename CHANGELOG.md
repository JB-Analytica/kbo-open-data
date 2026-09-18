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

### Changed

- **Only the marts are published to MotherDuck.** `DESTINATION=motherduck` used to run the
  whole pipeline against MotherDuck: 41 million raw rows loaded there by dlt, with dbt
  building on top. It now means *where the published marts go*. dlt always loads into a
  local DuckDB file, dbt always builds against that file, and a new publish step
  (`ingest/publish.py`, `kbo publish`, `make deploy`) copies the five aggregate marts --
  276 rows, about 20 KB as Parquet -- into MotherDuck afterwards. Switching to
  MotherDuck is still a single environment variable with no model changes.

  The point is not the several GB of a 10 GB free tier, or the 41 million rows that no
  longer cross the network on every Flight run. It is that **the raw layer never leaves the
  machine it was loaded on, so the 770,434 natural persons in the register cannot reach a
  cloud account at all.** `dlt_destination` has no cloud branch left to take, which is a
  stronger guarantee than a filter would be.

  Consequences: `transform/profiles.yml` has one `duckdb` output and a fixed target instead
  of a `DESTINATION`-driven pair; the MotherDuck Flight loads and builds under `/tmp` (150 GB
  of container scratch) and verifies the marts in MotherDuck after publishing them; the CI
  MotherDuck job builds locally and publishes only the marts to `kbo_ci`. `make build` and
  `make demo` are unchanged and still credential-free. The publish path is tested against a
  second local DuckDB file, so it needs no account, token or network.

- The sector mart reads **NACE 2025 (Rev. 2.1)** by default instead of NACE 2008 (Rev. 2);
  `KBO_NACE_VERSION` still overrides it. This is not a relabelling: Rev. 2.1 has 22 sections
  (A–V) against Rev. 2's 21, and every division from 61 up sits one letter further along, so
  412,274 of the 742,028 companies with a 2025 main activity would have carried the wrong
  section letter under the old seed. The 2025 ranges come from the Eurostat `NACE_R2_1`
  codelist, whose item codes carry the section letter in front of the division.
- `nace_section` is now keyed by `nace_version` and carries **numbers only**. The section
  labels come from `stg_code` (category `Nace2008` / `Nace2025`) like every other coded
  concept in this project, so they are Dutch rather than hand-written English. A section
  letter missing from `code.csv` keeps its enterprises, labelled with the bare letter, and
  `assert_nace_section_mapping` fails the build when that happens.
- The seed's shape changed, so an existing warehouse needs one
  `dbt seed --full-refresh --select nace_section`. A fresh clone needs nothing.

### Changed

- The extract reads through pyarrow rather than a row-by-row Python loop, and dlt hands
  DuckDB Parquet instead of INSERT statements. A full real extract loads in **41 seconds**
  where it took about 35 minutes.
- Write disposition comes from `meta.csv`'s `ExtractType`. A full extract is a complete
  restatement, so it uses `replace`; an update file keeps `merge` on the primary keys.
  `meta` and `code` are always replaced, since they restate in full either way. Dropping
  merge on full loads also removes dlt's duplicate staging dataset: the warehouse is
  895 MB where it was 1.9 GB.
- `activity` now holds 34,463,639 rows rather than 34,462,748. The file genuinely contains
  891 exact duplicate rows, which `merge` was silently collapsing because the whole row is
  the key. No published figure changes.

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
