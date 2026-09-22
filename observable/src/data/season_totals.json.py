"""season_totals.json.py — per-season aggregate stats for all leagues."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

rows = query(
    """
    select
        league_id,
        season,
        count(*)                                                             as matches,
        coalesce(sum(home_goals + away_goals), 0)                           as goals,
        count(*) filter (where home_goals > away_goals)                     as home_wins,
        count(*) filter (where home_goals < away_goals)                     as away_wins,
        count(*) filter (where home_goals = away_goals and home_goals is not null) as draws
    from core.match
    group by league_id, season
    order by league_id, season desc
    """
)

emit_json(rows)
