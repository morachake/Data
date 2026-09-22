"""standings.json.py — standings for all leagues and seasons."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

rows = query(
    """
    select
        s.league_id,
        s.season,
        s.position,
        coalesce(t.name, s.team_id) as team_name,
        s.played,
        s.won,
        s.drawn,
        s.lost,
        s.goals_for,
        s.goals_against,
        s.goal_diff,
        s.points
    from core.standings s
    left join core.team t on t.team_id = s.team_id
    order by s.league_id, s.season, s.position
    """
)

emit_json(rows)
