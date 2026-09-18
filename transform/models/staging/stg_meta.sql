with source as (

    select * from {{ source('kbo_raw', 'meta') }}

),

renamed as (

    select
        -- KBO writes dates day-first (07-09-2026 is 7 September). Reading it any other
        -- way silently produces a plausible wrong date.
        max(case when trim(variable) = 'SnapshotDate'
            then strptime(nullif(trim(value), ''), '%d-%m-%Y')::date end)
            as snapshot_date,
        max(case when trim(variable) = 'ExtractType' then nullif(trim(value), '') end) as extract_type,
        max(case when trim(variable) = 'ExtractNumber' then nullif(trim(value), '') end) as extract_number
    from source

)

select * from renamed
