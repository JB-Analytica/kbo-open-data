{#-
    The one place the small-cell suppression rule lives.

    Given an already-aggregated CTE, every cell whose `count_column` is below
    `var('min_cell_size')` is rolled into a single row flagged `is_suppressed_bucket`.
    If that combined row is itself below the threshold it is dropped entirely -- a
    "suppressed" row of 3 would be just as re-identifying as the cells it hides.

    `share_of_total` is computed over the rows that actually survive, so the published
    shares always add to 1 and never hint at how much was removed.

    Arguments
      relation          name of the CTE holding one row per cell
      count_column      the aggregate being protected (default enterprise_count)
      label_columns     columns set to 'Other (suppressed)' on the bucket row
      null_columns      columns set to NULL on the bucket row (codes, ids, numeric keys)
      literal_columns   {column: sql literal} for the bucket row (e.g. a sort order)
      carry_columns     columns constant across the relation, carried through as-is
-#}
{% macro suppress_small_cells(
    relation,
    count_column='enterprise_count',
    label_columns=[],
    null_columns=[],
    literal_columns={},
    carry_columns=['snapshot_date']
) %}

{%- set dimension_columns = carry_columns + null_columns + label_columns + literal_columns.keys() | list -%}
{%- set threshold = var('min_cell_size') -%}

kept as (

    select
        {%- for column in dimension_columns %}
        {{ column }},
        {%- endfor %}
        {{ count_column }},
        false as is_suppressed_bucket
    from {{ relation }}
    where {{ count_column }} >= {{ threshold }}

),

suppressed as (

    select
        {%- for column in carry_columns %}
        max({{ column }}) as {{ column }},
        {%- endfor %}
        {%- for column in null_columns %}
        null as {{ column }},
        {%- endfor %}
        {%- for column in label_columns %}
        cast('Other (suppressed)' as varchar) as {{ column }},
        {%- endfor %}
        {%- for column, value in literal_columns.items() %}
        {{ value }} as {{ column }},
        {%- endfor %}
        sum({{ count_column }}) as {{ count_column }},
        true as is_suppressed_bucket
    from {{ relation }}
    where {{ count_column }} < {{ threshold }}
    having sum({{ count_column }}) >= {{ threshold }}

),

published as (

    select * from kept
    union all
    select * from suppressed

),

final as (

    select
        {%- for column in dimension_columns %}
        {{ column }},
        {%- endfor %}
        -- `union all` of a count() and a sum() widens to HUGEINT, which lands in Parquet
        -- as a decimal. A published head-count should read as a whole number.
        cast({{ count_column }} as bigint) as {{ count_column }},
        round(
            {{ count_column }} * 1.0 / nullif(sum({{ count_column }}) over (), 0), 6
        ) as share_of_total,
        is_suppressed_bucket
    from published

)

select * from final

{% endmacro %}
