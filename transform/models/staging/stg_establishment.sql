with source as (

    select * from {{ source('kbo_raw', 'establishment') }}

),

renamed as (

    select
        nullif(trim(establishment_number), '') as establishment_number,
        nullif(trim(enterprise_number), '') as enterprise_number,
        strptime(nullif(trim(start_date), ''), '%d-%m-%Y')::date as start_date,
        _dlt_load_id as dlt_load_id
    from source

)

select * from renamed
