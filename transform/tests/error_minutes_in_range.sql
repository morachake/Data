-- ERROR level test
-- Every appearance record must have minutes_played between 0 and 120.
-- Returns out-of-range rows.

select
    appearance_id,
    match_id,
    player_id,
    minutes_played
from {{ ref('appearance') }}
where
    minutes_played is not null
    and (minutes_played < 0 or minutes_played > 120)
