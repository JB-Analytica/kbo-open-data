with source as (

    select * from {{ source('kbo_raw', 'activity') }}

),

renamed as (

    select
        nullif(trim(entity_number), '') as entity_number,
        nullif(trim(activity_group), '') as activity_group_code,
        nullif(trim(nace_version), '') as nace_version,
        -- Text, not a number: NACE codes like 01130 lose their leading zero as an integer.
        nullif(trim(nace_code), '') as nace_code,
        nullif(trim(classification), '') as classification_code,
        _dlt_load_id as dlt_load_id
    from source

)

select * from renamed
