with source as (

    select * from {{ source('kbo_raw', 'enterprise') }}

),

renamed as (

    select
        nullif(trim(enterprise_number), '') as enterprise_number,
        nullif(trim(status), '') as status_code,
        nullif(trim(juridical_situation), '') as juridical_situation_code,
        nullif(trim(type_of_enterprise), '') as type_of_enterprise_code,
        -- Natural persons carry no legal form; KBO writes an empty string, we mean NULL.
        nullif(trim(juridical_form), '') as juridical_form_code,
        strptime(nullif(trim(start_date), ''), '%d-%m-%Y')::date as start_date,
        _dlt_load_id as dlt_load_id
    from source

)

select * from renamed
