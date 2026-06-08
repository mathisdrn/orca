{{ config(
    description="Cleaned and normalized staging model for the house prices dataset"
) }}

with source as (
    select * from {{ source('a_raw', 'house_prices') }}
),

renamed as (
    select
        price as price_usd,
        area as area_sqft,
        bedrooms as count_bedrooms,
        bathrooms as count_bathrooms,
        stories as count_stories,
        case when mainroad = 'yes' then true else false end as has_mainroad,
        case when guestroom = 'yes' then true else false end as has_guestroom,
        case when basement = 'yes' then true else false end as has_basement,
        case when hotwaterheating = 'yes' then true else false end as has_hotwater_heating,
        case when airconditioning = 'yes' then true else false end as has_air_conditioning,
        parking as count_parking_slots,
        case when prefarea = 'yes' then true else false end as is_preferred_area,
        furnishingstatus as furnishing_status
    from source
)

select * from renamed
