{{
  config(
    materialized='table',
    tags=['core']
  )
}}

/*
  player — canonical player entities post entity-resolution.

  Phase 1: sourced from staging.players (Wikipedia infobox scrape).
  Phase 2: entity_resolution/ will deduplicate and assign stable player_id.
  The player_id here is the Wikipedia title normalised to a slug until
  entity resolution is implemented.
*/

with base as (
    select
        player_id,
        wiki_title,
        full_name,
        date_of_birth,
        place_of_birth,
        height,
        position,
        current_club,
        nationality,
        wikidata_id,
        image_url,
        source_url
    from {{ source('staging', 'players') }}
)

select
    b.player_id,
    coalesce(b.full_name, b.wiki_title)  as full_name,
    b.wiki_title                          as known_as,
    -- Nationality: clean up common prefixes ("Retired South African" → "South African")
    regexp_replace(
        b.nationality,
        '^(Retired|Former|Dual|Professional|Late)\s+',
        '',
        'i'
    )                                     as nationality,
    case
        -- Already ISO: "1991-03-26" or embedded in Wikipedia template
        when b.date_of_birth ~ '\d{4}-\d{2}-\d{2}'
            then (regexp_match(b.date_of_birth, '(\d{4}-\d{2}-\d{2})'))[1]::date
        -- "DD Month YYYY" with optional footnotes, e.g. "4 September 1981 [ 1 ]"
        when b.date_of_birth ~ '^\d{1,2}\s+[A-Za-z]+\s+\d{4}'
            then to_date(
                regexp_replace(b.date_of_birth, '\s*\[.*?\]|\s*\(.*?\)', '', 'g'),
                'DD Month YYYY'
            )
        -- "Month DD, YYYY" e.g. "April 10, 1950"
        when b.date_of_birth ~ '^[A-Za-z]+\s+\d{1,2},?\s+\d{4}'
            then to_date(
                regexp_replace(b.date_of_birth, ',', '', 'g'),
                'Month DD YYYY'
            )
        -- Year-only, e.g. "1959" or "c. 1939 (age …)" or "1951 ( 1951 )"
        when b.date_of_birth ~ '\d{4}'
            then make_date(
                (regexp_match(b.date_of_birth, '(\d{4})'))[1]::int, 1, 1
            )
        else null
    end                                   as date_of_birth,
    case
        -- High confidence only when we have a full YYYY-MM-DD (exact date known)
        when b.date_of_birth ~ '\d{4}-\d{2}-\d{2}'
                or b.date_of_birth ~ '^\d{1,2}\s+[A-Za-z]+\s+\d{4}'
                or b.date_of_birth ~ '^[A-Za-z]+\s+\d{1,2},?\s+\d{4}'
            then 'high'
        -- Medium: year-only or approximate
        when b.date_of_birth ~ '\d{4}'
            then 'medium'
        else 'unknown'
    end                                   as dob_confidence,
    b.place_of_birth,
    b.position,
    case
        -- Match pure-integer strings like "179" (cm); skip "1.79 m (5 ft 10 in)" style
        when b.height ~ '^\d+$'
            then b.height::int
        -- Match decimal metre values like "1.79"
        when b.height ~ '^\d+\.\d+$'
            then round(b.height::numeric * 100)::int
        else null
    end                                   as height_cm,
    b.wikidata_id,
    b.image_url,
    -- Raw current club name from Wikipedia infobox (used as fallback display name)
    nullif(trim(b.current_club), '')      as current_club_raw
from base b
