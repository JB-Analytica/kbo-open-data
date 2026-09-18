-- The alarm for: the natural-person exclusion being weakened, reordered or joined away.
-- KBO's natural persons are sole traders; their registered address is their home address.
-- Not one of them may reach the spine, and therefore not one may reach a mart.

with natural_person_code as (

    select code
    from {{ ref('int_code_resolution') }}
    where concept = 'natural_person'

),

final as (

    select
        int_active_enterprise.enterprise_number
    from {{ ref('int_active_enterprise') }} as int_active_enterprise
    inner join {{ ref('stg_enterprise') }} as stg_enterprise
        on stg_enterprise.enterprise_number = int_active_enterprise.enterprise_number
    inner join natural_person_code
        on natural_person_code.code = stg_enterprise.type_of_enterprise_code

)

select * from final
