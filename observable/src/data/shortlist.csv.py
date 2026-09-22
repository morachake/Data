"""shortlist.csv.py — full mart.shortlist snapshot (all scout rows)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_csv

rows = query(
    """
    select
        player_id,
        full_name,
        known_as,
        nationality,
        date_of_birth,
        dob_confidence,
        place_of_birth,
        height_cm,
        image_url,
        wikidata_id,
        position,
        position_bucket,
        season_id,
        league_id,
        season,
        league_name,
        -- rename to match Streamlit conventions
        age_at_midpoint      as age,
        data_tier            as tier,
        current_team_name    as club,
        talent_score,
        appearances,
        starts,
        minutes_played,
        goals,
        goals_per90,
        assists,
        assists_per90,
        own_goals,
        yellow_cards,
        red_cards,
        clean_sheets,
        minutes_share,
        starts_share,
        goals_per90_pct_league,
        minutes_share_pct_league,
        goals_per90_pct_continental,
        minutes_share_pct_continental,
        prev_minutes_share,
        prev_goals_per90,
        minutes_share_delta,
        goals_per90_delta,
        career_appearances,
        career_goals,
        career_clubs,
        career_goals_per_app,
        injury_notes,
        -- GK columns
        conceded_p90,
        expected_p90,
        goals_prevented_p90,
        clean_sheet_rate,
        gk_talent_score,
        gk_sample_confidence,
        gk_conceded,
        gk_expected,
        gk_age_band,
        gk_pct_minutes_share,
        gk_pct_goals_prevented,
        gk_pct_clean_sheets,
        -- composites
        comp_minutes_share,
        comp_output_per90,
        comp_position_pct,
        comp_age_factor,
        comp_progression,
        comp_league_strength
    from mart.shortlist
    order by talent_score desc nulls last
    """
)

emit_csv(rows)
