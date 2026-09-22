"""leagues.json.py — list of competitions with their available seasons."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

leagues = query(
    """
    select
        c.competition_id,
        c.name,
        c.country,
        c.type,
        c.wave,
        array_agg(distinct s.season order by s.season desc) as seasons
    from core.competition c
    left join core.standings s on s.league_id = c.competition_id
    group by c.competition_id, c.name, c.country, c.type, c.wave
    order by
        (array_agg(distinct s.season) filter (where s.season is not null) is not null) desc,
        c.wave,
        c.competition_id
    """
)

emit_json(leagues)
