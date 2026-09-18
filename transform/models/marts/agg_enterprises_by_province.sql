with active_enterprise as (

    select * from {{ ref('int_active_enterprise') }}

),

zipcode_province as (

    select * from {{ ref('zipcode_province') }}

),

postcodes as (

    select
        enterprise_number,
        snapshot_date,
        try_cast(zipcode as integer) as zipcode_numeric
    from active_enterprise

),

cells as (

    select
        postcodes.snapshot_date,
        coalesce(zipcode_province.province_code, 'UNK') as province_code,
        coalesce(zipcode_province.province_name_en, 'Unknown') as province_name,
        coalesce(zipcode_province.region_en, 'Unknown') as region_name,
        count(*) as enterprise_count
    from postcodes
    left join zipcode_province
        on postcodes.zipcode_numeric between zipcode_province.zip_from and zipcode_province.zip_to
    group by 1, 2, 3, 4

),

{{ suppress_small_cells(
    relation='cells',
    label_columns=['province_name', 'region_name'],
    null_columns=['province_code']
) }}
