-- The alarm for: a new mart being added without going through suppress_small_cells, or the
-- macro's threshold being bypassed. A published cell below var('min_cell_size') is a
-- re-identification risk in a thin slice, which is the whole reason the rule exists.

{% set marts = [
    'agg_enterprises_by_legal_form',
    'agg_enterprises_by_nace_section',
    'agg_enterprises_by_province',
    'agg_enterprises_by_start_year',
    'agg_establishments_per_enterprise'
] %}

with all_cells as (

    {% for mart in marts %}
    select
        '{{ mart }}' as mart_name,
        enterprise_count
    from {{ ref(mart) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

final as (

    select *
    from all_cells
    where enterprise_count < {{ var('min_cell_size') }}

)

select * from final
