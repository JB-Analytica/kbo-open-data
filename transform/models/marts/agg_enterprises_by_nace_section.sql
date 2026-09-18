with active_enterprise as (

    select * from {{ ref('int_active_enterprise') }}

),

nace_section as (

    select * from {{ ref('nace_section') }}

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
        coalesce(nace_section.section_label_en, 'Unknown') as nace_section_label,
        count(*) as enterprise_count
    from divisions
    left join nace_section
        on divisions.division between nace_section.division_from and nace_section.division_to
    group by 1, 2, 3

),

{{ suppress_small_cells(
    relation='cells',
    label_columns=['nace_section_label'],
    null_columns=['nace_section']
) }}
