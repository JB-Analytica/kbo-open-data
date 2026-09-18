with source as (

    select * from {{ source('kbo_raw', 'code') }}

),

renamed as (

    select
        nullif(trim(category), '') as category,
        nullif(trim(code), '') as code,
        nullif(upper(trim(language)), '') as language,
        nullif(trim(description), '') as description
    from source

),

ranked as (

    select
        category,
        code,
        description,
        -- The only place in the project where language preference is decided.
        row_number() over (
            partition by category, code
            order by case language when 'NL' then 1 when 'EN' then 2 when 'FR' then 3 else 4 end
        ) as language_rank
    from renamed
    where description is not null

),

final as (

    select
        category,
        code,
        description
    from ranked
    where language_rank = 1

)

select * from final
