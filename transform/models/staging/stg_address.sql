with source as (

    select * from {{ source('kbo_raw', 'address') }}

),

renamed as (

    select
        nullif(trim(entity_number), '') as entity_number,
        nullif(trim(type_of_address), '') as type_of_address_code,
        nullif(trim(zipcode), '') as zipcode,
        -- Kept as-is: a struck-off address is still a row, it is just no longer current.
        strptime(nullif(trim(date_striking_off), ''), '%d-%m-%Y')::date as date_striking_off,
        _dlt_load_id as dlt_load_id
    from source

)

select * from renamed
