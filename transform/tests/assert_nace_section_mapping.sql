-- The alarm for: the sector mart mislabelling or losing enterprises when the NACE version
-- changes. Moving from 2008 to 2025 is not a relabelling -- Rev. 2.1 reassigns divisions
-- between sections -- and the failure mode is silent: every division still falls inside
-- *some* seeded range, just the wrong one, and every count still adds up.
--
-- Four things must hold, and none of them is checked by a schema test:
--
--   ambiguous_division  a division in the data resolves to more than one section, or to
--                       none at all, for the configured version. Overlapping or gapped
--                       seed ranges are how a whole sector silently doubles or disappears.
--   unlabelled_section  a section letter got no row out of stg_code, so the mart is
--                       publishing a bare letter as its label. The mart deliberately keeps
--                       the enterprises in that case; this is what makes that visible.
--   enterprises_lost    the mart totals less than the spine by more than suppression can
--                       account for. A dropped suppressed bucket is by construction below
--                       var('min_cell_size'), so any larger gap is a join that ate rows.

with spine as (

    select
        enterprise_number,
        case
            when nace_code is null then null
            else try_cast(substr(nace_code, 1, 2) as integer)
        end as division
    from {{ ref('int_active_enterprise') }}

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

    select code
    from {{ ref('stg_code') }}
    where category = 'Nace{{ var("nace_version") }}'
        and length(code) = 1

),

division_sections as (

    select
        spine.division,
        count(distinct nace_section.section) as section_count
    from spine
    left join nace_section
        on spine.division between nace_section.division_from and nace_section.division_to
    where spine.division is not null
    group by 1

),

ambiguous_division as (

    select
        'ambiguous_division' as failure,
        cast(division as varchar) as detail,
        section_count as observed
    from division_sections
    where section_count <> 1

),

unlabelled_section as (

    select
        'unlabelled_section' as failure,
        nace_section.section as detail,
        0 as observed
    from nace_section
    left join section_label
        on section_label.code = nace_section.section
    where section_label.code is null

),

enterprises_lost as (

    select
        'enterprises_lost' as failure,
        cast(spine_count - mart_count as varchar) as detail,
        mart_count as observed
    from (
        select
            (select count(*) from spine) as spine_count,
            (select coalesce(sum(enterprise_count), 0)
             from {{ ref('agg_enterprises_by_nace_section') }}) as mart_count
    )
    where spine_count - mart_count >= {{ var('min_cell_size') }}

),

final as (

    select * from ambiguous_division
    union all
    select * from unlabelled_section
    union all
    select * from enterprises_lost

)

select * from final
