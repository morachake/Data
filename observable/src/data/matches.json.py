"""matches.json.py — all matches with team names."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

rows = query(
    """
    select
        m.match_id,
        m.league_id,
        m.season,
        m.match_date,
        coalesce(ht.name, m.home_team_id) as home,
        coalesce(at2.name, m.away_team_id) as away,
        m.home_goals,
        m.away_goals,
        case
            when m.home_goals > m.away_goals  then 'H'
            when m.home_goals < m.away_goals  then 'A'
            when m.home_goals = m.away_goals  then 'D'
            else null
        end as result
    from core.match m
    left join core.team ht  on ht.team_id  = m.home_team_id
    left join core.team at2 on at2.team_id = m.away_team_id
    order by m.league_id, m.season, m.match_date nulls last
    """
)

emit_json(rows)
