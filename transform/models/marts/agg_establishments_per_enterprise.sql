with active_enterprise as (

    select * from {{ ref('int_active_enterprise') }}

),

bucketed as (

    select
        snapshot_date,
        case
            when establishment_count = 0 then '0'
            when establishment_count = 1 then '1'
            when establishment_count = 2 then '2'
            when establishment_count between 3 and 5 then '3-5'
            when establishment_count between 6 and 10 then '6-10'
            else '11+'
        end as establishment_bucket,
        case
            when establishment_count = 0 then 1
            when establishment_count = 1 then 2
            when establishment_count = 2 then 3
            when establishment_count between 3 and 5 then 4
            when establishment_count between 6 and 10 then 5
            else 6
        end as bucket_sort_order
    from active_enterprise

),

cells as (

    select
        snapshot_date,
        establishment_bucket,
        bucket_sort_order,
        count(*) as enterprise_count
    from bucketed
    group by 1, 2, 3

),

{{ suppress_small_cells(
    relation='cells',
    label_columns=['establishment_bucket'],
    literal_columns={'bucket_sort_order': 99}
) }}
