-- The alarm for: two extracts being mixed in one publish, or a mart losing its attribution.
-- Every mart must carry the same non-null snapshot_date, because the five of them are
-- published together as one picture of one day.

{% set marts = [
    'agg_enterprises_by_legal_form',
    'agg_enterprises_by_nace_section',
    'agg_enterprises_by_province',
    'agg_enterprises_by_start_year',
    'agg_establishments_per_enterprise'
] %}

with all_dates as (

    {% for mart in marts %}
    select
        '{{ mart }}' as mart_name,
        snapshot_date
    from {{ ref(mart) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

final as (

    select
        count(distinct snapshot_date) as distinct_dates,
        count(*) filter (where snapshot_date is null) as null_dates
    from all_dates
    having count(distinct snapshot_date) <> 1
        or count(*) filter (where snapshot_date is null) > 0

)

select * from final
