"""coverage.json.py — data-quality coverage metrics per league-season."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

rows = query(
    """
    select
        lsc.season_id,
        s.competition_id,
        coalesce(comp.name, s.competition_id) as league_name,
        lsc.tier,
        lsc.pct_matches_with_result,
        lsc.pct_goals_with_scorer,
        lsc.pct_matches_with_lineups,
        lsc.pct_players_with_dob,
        lsc.computed_at
    from core.league_season_coverage lsc
    join  core.season      s    on s.season_id      = lsc.season_id
    left join core.competition comp on comp.competition_id = s.competition_id
    order by s.competition_id, lsc.season_id desc
    """
)

emit_json(rows)
