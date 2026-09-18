-- The alarm for: stg_code's language preference stopping collapsing the code table, which
-- would fan every code-resolution join out by up to three and triple the counts that
-- reach the marts. The grain is one row per (category, code).

with final as (

    select
        category,
        code,
        count(*) as row_count
    from {{ ref('stg_code') }}
    group by category, code
    having count(*) > 1

)

select * from final
