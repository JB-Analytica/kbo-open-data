# kbo-open-data

Built by [JB Analytica](https://github.com/JB-Analytica).

**The Belgian company register, turned into five published aggregates that answer one
question: what does the Belgian company population actually look like?**

Legal form, sector, province, start-year cohort. Nothing else. The register itself is 2.2 GB
of CSVs behind a registration wall — 42 million rows, 39% of the entities in it private
individuals. What almost everyone actually wants from it is a few hundred rows of aggregates,
and those fit in 20 KB.

So that is what this repo produces, and the aggregates are committed here. You can answer
the question without registering with anybody, installing anything, or running a query.

## The numbers

From the extract of **17 September 2026**. Every figure below is in `data/published/`, which
is 20 KB of Parquet in this repository — no registration, no account, no query needed.

**1,193,029 active companies**, once the 770,434 natural persons are excluded. That is 39% of
the register removed before anything is published.

| Establishments | Companies | Share |
|---|---:|---:|
| 0 | 378,140 | 31.7% |
| 1 | 755,675 | 63.3% |
| 2 | 44,257 | 3.7% |
| 3–5 | 10,923 | 0.9% |
| 6–10 | 2,251 | 0.19% |
| 11+ | 1,783 | 0.15% |

**95% of Belgian companies operate from one location or none.** Fewer than 1 in 250 has more
than five. Whatever else the register is, it is not a country of large organisations.

The top legal forms: Besloten Vennootschap 537,877 (45.1%), Vereniging zonder winstoogmerk
140,901 (11.8%), Vereniging van mede-eigenaars 112,892 (9.5%), Naamloze vennootschap 78,210
(6.6%), BVBA under the old statute 72,023 (6.0%). The long tail is 84 published forms and one
suppressed row of 39 companies spread over 19 forms.

By province: Antwerp 199,161 (16.7%), Brussels-Capital 174,233 (14.6%), East Flanders 141,171
(11.8%), West Flanders 131,152 (11.0%), Flemish Brabant 114,986 (9.6%). Roughly 56% of
companies sit in Flanders, 21% in Wallonia, 15% in Brussels, and 7.9% cannot be placed — see
the caveats below.

By sector, once the 38% with no declared activity are set aside: professional, scientific and
technical services 148,540 (12.4%), wholesale and retail 106,699 (8.9%), construction 92,667
(7.8%), accommodation and food 43,991 (3.7%), real estate 43,582 (3.7%), telecoms and IT
41,335 (3.5%). Sections follow **NACE Rev. 2.1**, which KBO publishes as `Nace2025`, and the
labels come from KBO's own code table rather than a translation of ours.

Start-year cohorts run from 1800 to 2026 across 151 published years, peaking in the most
recent three (2025: 65,859; 2024: 63,950; 2023: 59,975). Read that with the survivorship
caveat below, which is the whole point of it.

### What the numbers do not say

Two gaps are large enough that hiding them would be dishonest:

- **38% of companies have no NACE 2025 sector**, and appear as a single `Unknown` row rather
  than being dropped. 742,028 of 1,193,029 declare a main activity in NACE 2025 — better than
  the 643,817 (54%) that declare one in NACE 2008, which is why the sector mart now reads the
  2025 classification by default. Setting `KBO_NACE_VERSION=2008` switches it back.
- **7.9% (93,894) have no usable province.** 10,830 registered-office addresses carry a blank
  postcode, 17,775 are struck off, 37,771 are foreign, and 27,518 are numeric postcodes that
  fall outside every seeded range. They are an explicit `Unknown` row, never silently dropped.

## Attribution

Required by the KBO Open Data conditions of use (article 2.8), which oblige a reuser to
name the source and the date of the data update:

```
Source: Kruispuntbank van Ondernemingen (KBO/BCE), FOD Economie.
Data update: {snapshot_date}.
```

`{snapshot_date}` comes from `meta.csv` in the extract — the date of the *data update*,
never the date the pipeline ran. Every published table carries it as a column, so the
attribution travels with the data rather than living only in this file.

## What is not in here, on purpose

The register includes sole traders registered as natural persons. Their name and address
are personal data. This pipeline is built so that none of it can leak, in three independent
layers:

1. **A column-level allowlist at the extract step.** `ingest/kbo_source.py` opens only the
   seven files it needs and reads only the columns listed in one table at the top of that
   module. `denomination.csv` (company and person names) and `contact.csv` (e-mail, phone,
   web) are never opened at all. Street, house number, box and municipality stay in the zip;
   for a sole trader those are a home address, and a postcode is all an aggregate needs.
2. **Natural-person entities are excluded at the model level**, in `int_active_enterprise`,
   so they cannot reach a mart — not hidden at display time, not filtered in a chart.
3. **Small-cell suppression.** Any aggregate cell below five entities is rolled into a
   single `Other (suppressed)` row, and if that row is itself below five it is dropped.
   Cheap insurance against re-identification in a thin slice.

No company-level row is published, anywhere. The practical effect is that the GDPR surface
of the published artefact is zero, and a test proves it: the suite scans every text column
of every loaded table for anything resembling a name or a contact detail.

Two related obligations, for completeness: the conditions of use forbid using KBO personal
data for direct marketing (article 2.2), and impose the usual GDPR duties toward natural
persons (article 2.1). Both are answered by not having the data. If anyone ever adds a
contact-extraction feature, that reasoning has to be redone from scratch.

## The honest caveat

**KBO holds only currently active entities, and carries no history.** Any trend built from
`StartDate` is a survivorship-biased cohort view, not company demography. A company that
started in 2005 and closed in 2012 is simply absent from every snapshot, so the older
cohorts are systematically thinner than they were. The start-year chart shows how many
companies founded in year X are *still alive today* — which is a real and interesting thing,
but it is not a founding-rate time series and must not be read as one.

KBO also holds no employee counts and no financial figures, so company size cannot be
measured directly. The proxies available here are type of enterprise, legal form, and
establishments per enterprise. Real size distribution would come from the NBB Central
Balance Sheet Office extract; that is deliberately out of scope for version one, and the
pipeline leaves a clean seam for it.

## What you need first

- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- For a real run: a KBO extract. **There is no anonymous download.** Register (free) at
  [kbopub.economie.fgov.be/kbo-open-data](https://kbopub.economie.fgov.be/kbo-open-data),
  accept the conditions of use, download the **full** zip, and drop it in `data/raw/`.
  A full file and an update file are published daily and kept for 31 days. (The cookbook
  and licence PDFs still say "first Sunday of the month". They are stale.)
- No MotherDuck account, no cloud warehouse, no credentials.

## Quick start

Without a KBO registration, on synthetic data with the real file and column layout:

```bash
make demo
```

That writes a fake extract, loads it, builds every model, runs 121 tests and exports five
Parquet files to `data/demo/`. It is also what CI runs on every pull request, because
"a clean clone works with no credentials" is only a promise if something keeps checking it.

With a real extract:

```bash
cp .env.example .env     # set KBO_ZIP to the zip you downloaded
make build
```

`make build` loads, transforms and publishes to `data/published/`. Default destination is a
local DuckDB file. No account is involved at any point.

## Deploying to MotherDuck (optional)

One environment variable, no model changes — the dbt project has one profile with two
targets and no model knows which one it is running on.

```bash
export DESTINATION=motherduck
export MOTHERDUCK_TOKEN=...   # a service account token, not a personal one
make build
```

`flight/` holds the version-controlled definition of a MotherDuck Flight that refreshes the
marts daily on MotherDuck's own runtime. `dive/` documents the published visualisation.
Both have their own README, including the two things still unresolved: the exact hour the
KBO daily file appears, and whether SFTP access has been granted.

## Working on it

```bash
uv sync --extra dev
make test          # ruff, ty, pytest
make demo          # the fast loop: the whole pipeline in a couple of seconds
make clean
```

The tests that matter are not the unit tests. They are `assert_expected_codes_resolve`,
which fails the build if a KBO code the privacy design depends on ever disappears from an
extract, and `assert_no_natural_persons`, `assert_no_small_cells` and
`assert_mart_totals_reconcile`. Do not weaken them.

## Layout

```
ingest/           dlt source: the column allowlist, the loader, the CLI
transform/        dbt: staging -> intermediate -> five aggregate marts, seeds, tests
flight/           MotherDuck Flight definition, under version control
dive/             how the published Dive is built and shared
data/raw/         your KBO zip. Git-ignored, always.
data/published/   the aggregate Parquet. Committed, because it is the point.
tests/fixtures/   the synthetic extract everything is verified against
```

## Licence

Code: MIT, see `LICENSE`.

Data: the aggregates in `data/published/` are derived from KBO Open Data, reused under the
FOD Economie conditions of use, which permit reuse including commercial use and republication
subject to the attribution above. They contain no personal data.

## Credits

Data from the Kruispuntbank van Ondernemingen / Banque-Carrefour des Entreprises, published
as open data by FOD Economie, K.M.O., Middenstand en Energie.

Built on [dlt](https://dlthub.com), [DuckDB](https://duckdb.org), [dbt](https://getdbt.com)
and [MotherDuck](https://motherduck.com) — the same stack JB Analytica builds client
platforms on. See [reference-architecture](https://github.com/JB-Analytica/reference-architecture).
