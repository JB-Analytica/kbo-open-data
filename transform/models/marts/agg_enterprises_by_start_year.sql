with active_enterprise as (

    select * from {{ ref('int_active_enterprise') }}

),

cells as (

    select
        snapshot_date,
        start_year,
        count(*) as enterprise_count
    from active_enterprise
    group by 1, 2

),

{{ suppress_small_cells(
    relation='cells',
    null_columns=['start_year']
) }}
