{#-
    The spine. One row per enterprise that is a legal person AND active, with the one
    registered-office postcode, the one main NACE code in the configured version, and the
    number of establishments hanging off it.

    Natural persons are excluded HERE, not in the marts, so that no downstream model can
    reintroduce them by forgetting a filter.
-#}

with enterprise as (

    select * from {{ ref('stg_enterprise') }}

),

address as (

    select * from {{ ref('stg_address') }}

),

activity as (

    select * from {{ ref('stg_activity') }}

),

establishment as (

    select * from {{ ref('stg_establishment') }}

),

meta as (

    select * from {{ ref('stg_meta') }}

),

code_resolution as (

    select * from {{ ref('int_code_resolution') }}

),

resolved as (

    select
        max(case when concept = 'natural_person' then code end) as natural_person_code,
        max(case when concept = 'status_active' then code end) as status_active_code,
        max(case when concept = 'address_registered_office' then code end) as registered_office_code,
        max(case when concept = 'classification_main' then code end) as classification_main_code
    from code_resolution

),

eligible_enterprise as (

    select enterprise.*
    from enterprise
    cross join resolved
    where enterprise.type_of_enterprise_code is distinct from resolved.natural_person_code
        and enterprise.status_code = resolved.status_active_code

),

registered_office as (

    -- At most one address per enterprise. A current registered office only: an address
    -- with a striking-off date is historical and would place the company in the wrong province.
    select
        address.entity_number as enterprise_number,
        address.zipcode
    from address
    cross join resolved
    where address.type_of_address_code = resolved.registered_office_code
        and address.date_striking_off is null
    qualify row_number() over (
        partition by address.entity_number order by address.zipcode
    ) = 1

),

main_activity as (

    -- One NACE version only. activity.csv carries several, and summing across them
    -- double-counts every enterprise that has been reclassified.
    select
        activity.entity_number as enterprise_number,
        activity.nace_code,
        activity.nace_version
    from activity
    cross join resolved
    where activity.classification_code = resolved.classification_main_code
        and activity.nace_version = '{{ var("nace_version") }}'
    qualify row_number() over (
        partition by activity.entity_number order by activity.nace_code
    ) = 1

),

establishment_counts as (

    select
        enterprise_number,
        count(*) as establishment_count
    from establishment
    group by enterprise_number

),

final as (

    select
        eligible_enterprise.enterprise_number,
        eligible_enterprise.juridical_form_code,
        eligible_enterprise.start_date,
        extract(year from eligible_enterprise.start_date)::integer as start_year,
        registered_office.zipcode,
        main_activity.nace_code,
        main_activity.nace_version,
        coalesce(establishment_counts.establishment_count, 0)::integer as establishment_count,
        meta.snapshot_date
    from eligible_enterprise
    cross join meta
    left join registered_office
        on registered_office.enterprise_number = eligible_enterprise.enterprise_number
    left join main_activity
        on main_activity.enterprise_number = eligible_enterprise.enterprise_number
    left join establishment_counts
        on establishment_counts.enterprise_number = eligible_enterprise.enterprise_number

)

select * from final
