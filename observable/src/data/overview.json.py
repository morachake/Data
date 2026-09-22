"""overview.json.py — home page KPI snapshot."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query_one, query, emit_json

kpi = query_one(
    """
    select
        (select count(*) from core.competition where type = 'league')      as leagues,
        (select count(*) from core.match)                                   as matches,
        (select count(distinct player_id) from core.player)                 as players,
        (select round(avg(talent_score)::numeric, 1)
           from mart.shortlist
          where talent_score is not null)                                    as avg_talent
    """
)

# Coverage breakdown per league — join through core.season for competition_id
coverage = query(
    """
    select
        lsc.season_id,
        s.competition_id,
        coalesce(comp.name, s.competition_id) as league_name,
        lsc.tier,
        lsc.pct_matches_with_result,
        lsc.pct_goals_with_scorer,
        lsc.pct_matches_with_lineups,
        lsc.pct_players_with_dob
    from core.league_season_coverage lsc
    join  core.season      s    on s.season_id      = lsc.season_id
    left join core.competition comp on comp.competition_id = s.competition_id
    order by s.competition_id, lsc.season_id desc
    """
)

# Talent score distribution (20 buckets across 0-100)
histogram = query(
    """
    select
        width_bucket(talent_score, 0, 100, 20) as bucket,
        count(*)                               as count
    from mart.shortlist
    where talent_score is not null
    group by bucket
    order by bucket
    """
)

emit_json({
    "kpi":       kpi,
    "coverage":  coverage,
    "histogram": histogram,
})
