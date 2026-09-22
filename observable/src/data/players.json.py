"""players.json.py — career appearances and squad history.

Player profile data (name, image, club, score …) is already in shortlist.csv
and is derived client-side in players.md. This loader only adds career and
squad tables which don't exist in the shortlist mart.

Column notes:
  core.fct_player_career : player_id, full_name, years, club_raw, appearances, goals
  core.fct_player_squad  : player_name, wiki_title, season, club_raw, position,
                            shirt_no, appearances, goals  (NO player_id)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

# ── Career appearances ────────────────────────────────────────────────────────
career = query(
    """
    select
        player_id,
        years,
        club_raw  as club,
        appearances,
        goals
    from core.fct_player_career
    order by player_id, years
    """
)

# ── PSL squad history — attach player_id via core.player.known_as ─────────────
squad = query(
    """
    select
        p.player_id,
        s.season,
        s.club_raw    as club,
        s.position,
        s.shirt_no,
        s.appearances,
        s.goals
    from core.fct_player_squad s
    join core.player p on p.known_as = s.wiki_title
    order by p.player_id, s.season
    """
)

emit_json({
    "career": career,
    "squad":  squad,
})
