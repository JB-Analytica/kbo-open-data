# The KBO Open Data Dive

This file is the record of what the Dive contains and how it gets published. A Dive is
MotherDuck's published, shareable visualisation, created and edited in the MotherDuck UI
against the live tables -- there is nothing here to run or deploy. Treat this as the
spec a curator (or a future maintainer) reads before opening the editor.

## The one question

**What does the Belgian company population look like -- by legal form, sector,
province and start-year cohort?**

The Dive should make one argument implicitly, without a slide that says it out loud:
the overwhelming majority of Belgian companies are small, and their data fits
comfortably in DuckDB. That is MotherDuck's own thesis, argued with Belgian numbers
instead of a vendor claim. Let the panels carry it -- a distribution that visibly
collapses toward small companies says this more convincingly than a caption would.
Tone throughout: understated, numbers first.

## Panels

Five panels, one per mart. No sixth panel, no filter that turns this into a general
explorer.

1. **Legal form** (`agg_enterprises_by_legal_form`) -- horizontal bar, ranked by
   `enterprise_count`. A ranked list of a few dozen legal forms reads better sorted than
   as a pie; a pie with more than five or six slices stops being readable.
2. **Sector** (`agg_enterprises_by_nace_section`) -- horizontal bar or treemap by NACE
   section. Prefer the bar unless the section count makes a treemap noticeably clearer
   in practice -- a treemap can imply a part-of-whole precision the suppressed cells
   don't actually support.
3. **Province** (`agg_enterprises_by_province`) -- a small choropleth of Belgium's ten
   provinces plus Brussels, or a ranked bar if a map is not worth building for eleven
   regions. Explicitly out of scope: any drill-down to municipality. Province is the
   floor.
4. **Start-year cohort** (`agg_enterprises_by_start_year`) -- bar series over
   `snapshot_date`'s start-year buckets. This is the panel the survivorship caveat
   below applies to most directly, so the caption belongs right on this panel, not only
   in a shared footer.
5. **Establishments per enterprise** (`agg_establishments_per_enterprise`) -- a
   histogram or cumulative-share chart. This is the small-company argument in a single
   chart: most enterprises run out of one establishment, and the distribution should
   show that visually without a caption doing the work.

A sixth panel is a reasonable option only if it strengthens the same one question (for
example, a single KPI strip summarising total active enterprises and the snapshot
date) -- not a new question.

**Explicitly out of scope:** any company-level search or lookup (no company-level row
is ever published, by design -- see the repo's privacy rules), municipality-level
geography, and a filterable general-purpose explorer. One sharp question, done well,
beats five mediocre ones.

## The survivorship caveat

KBO holds only *currently active* entities and carries no history. Any trend built from
`StartDate` is a survivorship-biased cohort view, not company demography: a company that
started in 2005 and closed in 2012 is simply absent from every snapshot. This has to be
stated in the Dive itself, not only in this file -- it is exactly the kind of caveat
that makes a data person trust everything else on the page.

Suggested caption wording, placed directly under the start-year panel:

> Counts are of enterprises active on the snapshot date, grouped by their start year.
> Enterprises that started and later stopped in an earlier year are not counted here --
> this is a survivorship-biased view of who is still active, not a history of company
> formation and closure.

## Attribution footer

Verbatim, in the Dive's footer, parameterised on the snapshot date (the date from
`meta.csv`, not the date the Flight ran):

```
Source: Kruispuntbank van Ondernemingen (KBO/BCE), FOD Economie.
Data update: {snapshot_date}.
```

This is a licence obligation (KBO gebruiksvoorwaarden article 2.8), not a courtesy --
it belongs on every published view of this data, including the Dive.

## How a visitor gets the data

Two ways, in order of convenience:

1. **Attach the public read-only share** (see below) from within MotherDuck -- no
   download, always current.
2. **Read the committed Parquet in `data/published/`** directly, with no MotherDuck
   account at all. This is the no-account path the rest of the repo already promises,
   and the Dive's own footer or an "about this data" panel should say so.

## What is actually in the `kbo` database

Five mart tables in the `marts` schema, and nothing else -- 276 rows, about 20 KB as
Parquet. The raw register is never uploaded: the Flight loads and builds it in its own `/tmp` and
publishes only the aggregates, so the 770,434 natural persons in the register are not in
this database and cannot be reached through the share. A viewer attaching the share sees
the same five tables that are committed as Parquet in `data/published/`.

## Publishing the share

```sql
CREATE SHARE kbo_open_data FROM kbo (ACCESS UNRESTRICTED, VISIBILITY HIDDEN, UPDATE AUTOMATIC);
```

Zero-copy, metadata only -- this does not duplicate the data. `UPDATE AUTOMATIC` keeps
the share current as the Flight refreshes `kbo`, with no separate republish step. What is
shared is the five aggregate marts, because that is all the database contains.

**Open question, to check before submission, not to answer here:** a share is
attachable by MotherDuck users in the same cloud region as the source database. If the
marts live in the EU region and most Dive Gallery traffic is in the US, that could block
viewers from attaching the share (though the Parquet-in-`data/published/` path above
would still work for them). Check, before submitting to the gallery:

- which region the Flight's `kbo` database actually lives in;
- where gallery viewers typically are;
- whether MotherDuck supports publishing the same marts into a share in more than one
  region, and if so, what that costs to set up and keep in sync.

## The Dive Gallery submission

Publishing this Dive to MotherDuck's Dive Gallery is the point of the exercise, not an
afterthought once the panels exist. A curator reviewing it is looking at: whether the
one question is answered clearly in five or six panels without scope creep, whether the
survivorship caveat is visible on the page itself (not buried in a tooltip), whether the
attribution footer is present and correctly parameterised, and whether a viewer without
a MotherDuck account can still get the data. Check all four before submitting.
