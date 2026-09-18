{#-
    Sector split of the spine, in the NACE version var('nace_version') selects.

    Two separate things are needed to name a section, and they come from two separate
    places on purpose:

      * which section a division belongs to  -> the nace_section seed, numbers only.
        This genuinely is not in the extract; it is the structure of the classification,
        and it differs between versions (Rev. 2.1 moved every division from 61 up one
        letter along, and added V).
      * what that section is called          -> stg_code, category 'Nace' || the version.
        KBO publishes the single-character section codes right next to the five-digit
        ones, so there is no excuse for a hand-written label here. Same rule as every
        other coded concept in this project: code.csv is the only authority.

    A section letter with no row in the code table keeps its enterprises -- the letter
    stands in as the label -- rather than dropping them. assert_nace_section_mapping
    fails the build when that happens, so the fallback is a safety net, not a silence.
-#}

with active_enterprise as (

    select * from {{ ref('int_active_enterprise') }}

),

nace_section as (

    select
        division_from,
        division_to,
        section
    from {{ ref('nace_section') }}
    where nace_version = '{{ var("nace_version") }}'

),

section_label as (

    -- The section letters sit in the same category as the five-digit codes, as
    -- single-character codes. stg_code has already picked the preferred language.
    select
        code,
        description
    from {{ ref('stg_code') }}
    where category = 'Nace{{ var("nace_version") }}'
        and length(code) = 1

),

divisions as (

    select
        enterprise_number,
        snapshot_date,
        -- NACE codes are text precisely so 01130 keeps its leading zero; the division is
        -- the first two digits, read back as an integer for the range join.
        case
            when nace_code is null then null
            else try_cast(substr(nace_code, 1, 2) as integer)
        end as division
    from active_enterprise

),

cells as (

    select
        divisions.snapshot_date,
        coalesce(nace_section.section, 'Unknown') as nace_section,
        coalesce(
            section_label.description, nace_section.section, 'Unknown'
        ) as nace_section_label,
        count(*) as enterprise_count
    from divisions
    left join nace_section
        on divisions.division between nace_section.division_from and nace_section.division_to
    left join section_label
        on section_label.code = nace_section.section
    group by 1, 2, 3

),

{{ suppress_small_cells(
    relation='cells',
    label_columns=['nace_section_label'],
    null_columns=['nace_section']
) }}
