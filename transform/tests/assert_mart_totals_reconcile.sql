-- The alarm for: a fan-out join inventing enterprises. Suppression may remove rows, so a
-- mart total below the spine is expected; a mart total above it means an enterprise was
-- counted twice -- most likely a second address or a second main activity slipping through.

{% set marts = [
    'agg_enterprises_by_legal_form',
    'agg_enterprises_by_nace_section',
    'agg_enterprises_by_province',
    'agg_enterprises_by_start_year',
    'agg_establishments_per_enterprise'
] %}

with spine as (

    select count(*) as spine_count
    from {{ ref('int_active_enterprise') }}

),

mart_totals as (

    {% for mart in marts %}
    select
        '{{ mart }}' as mart_name,
        sum(enterprise_count) as mart_count
    from {{ ref(mart) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

final as (

    select
        mart_totals.mart_name,
        mart_totals.mart_count,
        spine.spine_count
    from mart_totals
    cross join spine
    where mart_totals.mart_count > spine.spine_count

)

select * from final
