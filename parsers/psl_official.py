"""
parsers/psl_official.py

Parses RawPageItem blocks (block_type='match_report') from the PSL official spider.
Produces stg_appearance and stg_goal rows.

Entry point: parse(raw_item) -> list[dict]
"""

from parsers.common.text import clean


def parse(raw_item: dict) -> list[dict]:
    """
    Parse one match_report RawPageItem and return stg_appearance and stg_goal rows.
    """
    if raw_item.get("block_type") != "match_report":
        return []

    payload = raw_item.get("payload") or {}
    lineups: dict = payload.get("lineups", {})
    goals: list = payload.get("goals", [])
    substitutions: list = payload.get("substitutions", [])

    league_id = raw_item.get("league_id", "RSA_PREM")
    season = raw_item.get("season", "")
    url = raw_item.get("url", "")
    source_id = raw_item.get("source_id", "psl_official")
    run_id = raw_item.get("run_id")
    fetched_at = raw_item.get("fetched_at")

    rows: list[dict] = []

    # ── Determine full-time minutes for each player using substitutions ──
    # Build a lookup: player_name → minutes_played
    # Default = 90 if started and not substituted off; 0 if on bench and not subbed on
    sub_off_at: dict[str, int] = {}
    sub_on_at: dict[str, int] = {}
    for sub in substitutions:
        if sub.get("player_off") and sub.get("minute"):
            sub_off_at[clean(sub["player_off"])] = sub["minute"]
        if sub.get("player_on") and sub.get("minute"):
            sub_on_at[clean(sub["player_on"])] = sub["minute"]

    # ── Appearances ────────────────────────────────────────────────────
    team_names = list(lineups.keys())
    home_team_raw = team_names[0] if len(team_names) > 0 else None
    away_team_raw = team_names[1] if len(team_names) > 1 else None

    for team_raw, players in lineups.items():
        for p in players:
            name = clean(p.get("name", ""))
            if not name:
                continue
            started = p.get("started", True)
            name_key = name.lower()
            if started:
                minutes = sub_off_at.get(name_key, 90)
            else:
                on_at = sub_on_at.get(name_key)
                minutes = (90 - on_at) if on_at else 0

            rows.append({
                "_row_type": "stg_appearance",
                "league_id": league_id,
                "season": season,
                "match_date": None,       # extracted by match resolver
                "home_team_raw": home_team_raw,
                "away_team_raw": away_team_raw,
                "player_raw": name,
                "team_raw": clean(team_raw),
                "started": started,
                "minutes_played": minutes,
                "shirt_number": p.get("shirt_number"),
                "position_raw": None,
                "source_id": source_id,
                "source_url": url,
                "run_id": run_id,
            })

    # ── Goals ─────────────────────────────────────────────────────────
    for g in goals:
        scorer = clean(g.get("scorer", ""))
        team = clean(g.get("team", ""))
        rows.append({
            "_row_type": "stg_goal",
            "league_id": league_id,
            "season": season,
            "match_date": None,
            "home_team_raw": home_team_raw,
            "away_team_raw": away_team_raw,
            "scorer_raw": scorer,
            "team_raw": team,
            "minute": g.get("minute"),
            "is_own_goal": g.get("is_own_goal", False),
            "is_penalty": g.get("is_penalty", False),
            "source_id": source_id,
            "source_url": url,
            "run_id": run_id,
        })

    return rows
