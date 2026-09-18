-- The alarm for: FOD Economie renaming, translating or removing a code description in a
-- future extract. Every concept must resolve to exactly one code. Zero means the privacy
-- filter silently stopped filtering; more than one means the match is too loose and we no
-- longer know which code we are excluding on. Either way, stop the build.

with expected as (

    select unnest([
        'natural_person',
        'legal_person',
        'status_active',
        'address_registered_office',
        'classification_main'
    ]) as concept

),

resolved as (

    select
        concept,
        count(*) as code_count
    from {{ ref('int_code_resolution') }}
    group by concept

),

final as (

    select
        expected.concept,
        coalesce(resolved.code_count, 0) as code_count
    from expected
    left join resolved on resolved.concept = expected.concept
    where coalesce(resolved.code_count, 0) <> 1

)

select * from final
