with active_enterprise as (

    select * from {{ ref('int_active_enterprise') }}

),

code as (

    select * from {{ ref('stg_code') }}

),

legal_form as (

    select
        code,
        description
    from code
    where category = 'JuridicalForm'

),

cells as (

    select
        active_enterprise.snapshot_date,
        active_enterprise.juridical_form_code as legal_form_code,
        coalesce(legal_form.description, 'Unknown') as legal_form_label,
        count(*) as enterprise_count
    from active_enterprise
    left join legal_form
        on legal_form.code = active_enterprise.juridical_form_code
    group by 1, 2, 3

),

{{ suppress_small_cells(
    relation='cells',
    label_columns=['legal_form_label'],
    null_columns=['legal_form_code']
) }}
