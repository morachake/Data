"""
serving/db.py — database query helpers for the Streamlit dashboard.

Covers:
  - Existing PSL standings/matches/player queries (backward compat)
  - New shortlist / talent mart queries (Phase 4)
"""

import io
import os
import time
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st
from dotenv import load_dotenv
from psycopg.rows import dict_row

CACHE_TTL = 300

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)


def dsn() -> str:
    return (
        f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
        f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']} "
        f"connect_timeout=10"
    )


def query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Execute *sql* and return results as a DataFrame.

    Retries once after a short pause on OperationalError (e.g. Docker TCP blip
    where the server closes an idle connection unexpectedly).
    """
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            with psycopg.connect(dsn(), row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            return pd.DataFrame(rows)
        except psycopg.OperationalError as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1)  # brief pause before retry
    raise last_exc  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# Existing queries (backward compat with dashboard/db.py)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL)
def seasons(league_id: str = "RSA_PREM") -> list[str]:
    frame = query(
        "select distinct season from core.standings where league_id = %s order by season desc",
        (league_id,),
    )
    return frame["season"].tolist() if not frame.empty else []


@st.cache_data(ttl=CACHE_TTL)
def leagues() -> list[str]:
    """Return all leagues that have at least one season of standings data."""
    frame = query(
        """
        select c.competition_id, c.name
        from core.competition c
        where c.type = 'league'
        order by
            -- leagues with data first
            (exists (select 1 from core.standings s where s.league_id = c.competition_id)) desc,
            c.wave, c.competition_id
        """
    )
    return frame["competition_id"].tolist() if not frame.empty else ["RSA_PREM"]


@st.cache_data(ttl=CACHE_TTL)
def league_info(competition_id: str) -> dict:
    """Return name and type for a competition."""
    frame = query(
        "select name, type, country, language from core.competition where competition_id = %s",
        (competition_id,),
    )
    if frame.empty:
        return {"name": competition_id, "type": "league", "country": "", "language": "en"}
    return frame.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL)
def standings(season: str, league_id: str = "RSA_PREM") -> pd.DataFrame:
    return query(
        """
        select
            s.position,
            coalesce(t.name, s.team_id)  as team_name,
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
        where s.season = %s and s.league_id = %s
        order by s.position
        """,
        (season, league_id),
    )


@st.cache_data(ttl=CACHE_TTL)
def matches(season: str, league_id: str = "RSA_PREM") -> pd.DataFrame:
    return query(
        """
        select
            coalesce(h.name, m.home_team_id)  as home,
            coalesce(a.name, m.away_team_id)  as away,
            m.home_goals,
            m.away_goals,
            m.result,
            m.source_url
        from core.match m
        left join core.team h on h.team_id = m.home_team_id
        left join core.team a on a.team_id = m.away_team_id
        where m.season = %s and m.league_id = %s
        order by h.name, a.name
        """,
        (season, league_id),
    )


@st.cache_data(ttl=CACHE_TTL)
def season_totals(season: str, league_id: str = "RSA_PREM") -> pd.DataFrame:
    return query(
        """
        select
            count(*)                                as matches,
            sum(home_goals + away_goals)            as goals,
            sum((result = 'H')::int)                as home_wins,
            sum((result = 'A')::int)                as away_wins,
            sum((result = 'D')::int)                as draws
        from core.match
        where season = %s and league_id = %s
        """,
        (season, league_id),
    )


@st.cache_data(ttl=CACHE_TTL)
def player_index() -> pd.DataFrame:
    """Return all known players with their latest club from shortlist or club spells."""
    return query(
        """
        select
            p.player_id,
            p.full_name,
            p.position,
            coalesce(s.current_team_name, sp.name) as current_club,
            p.date_of_birth,
            p.image_url
        from core.player p
        left join (
            select distinct on (player_id)
                player_id,
                current_team_name
            from mart.shortlist
            order by player_id, season_id desc nulls last
        ) s on s.player_id = p.player_id
        left join (
            select distinct on (cs.player_id)
                cs.player_id,
                t.name
            from core.player_club_spell cs
            join core.team t on t.team_id = cs.team_id
            order by cs.player_id, cs.start_season desc nulls last, cs.spell_id desc
        ) sp on sp.player_id = p.player_id
        order by p.full_name
        """
    )


@st.cache_data(ttl=CACHE_TTL)
def player_profile(player_id: str) -> pd.DataFrame:
    return query("select * from core.player where player_id = %s", (player_id,))


@st.cache_data(ttl=CACHE_TTL)
def player_career(player_id: str) -> pd.DataFrame:
    return query(
        """
        select years, club_raw as club, appearances, goals
        from core.fct_player_career
        where player_id = %s
        order by years
        """,
        (player_id,),
    )


@st.cache_data(ttl=CACHE_TTL)
def player_injuries(player_id: str) -> pd.DataFrame:
    return query(
        """
        select detail
        from core.fct_player_injuries
        where player_id = %s
        """,
        (player_id,),
    )


@st.cache_data(ttl=CACHE_TTL)
def player_squad(full_name: str, wiki_title: str) -> pd.DataFrame:
    return query(
        """
        select
            season,
            coalesce(team_name, club_raw) as club,
            position,
            shirt_no,
            appearances,
            goals
        from core.fct_player_squad
        where lower(player_name) = lower(%s)
           or lower(wiki_title)  = lower(%s)
        order by case when season = 'current' then 0 else 1 end, season desc
        """,
        (full_name, wiki_title),
    )


@st.cache_data(ttl=CACHE_TTL)
def player_season_stats(full_name: str) -> pd.DataFrame:
    return query(
        """
        select season, club_raw as club, stat_type, stat_value
        from core.fct_psl_player_stats
        where player_name = %s
        order by season desc, stat_type
        """,
        (full_name,),
    )


@st.cache_data(ttl=CACHE_TTL)
def player_shortlist_stats(player_id: str) -> pd.DataFrame:
    """Return per-season shortlist rows for a single player, newest first."""
    return query(
        """
        select
            league_name,
            season,
            position_bucket,
            talent_score,
            gk_talent_score,
            appearances,
            minutes_played,
            goals,
            goals_per90,
            conceded_p90,
            goals_prevented_p90,
            clean_sheet_rate,
            data_tier        as tier
        from mart.shortlist
        where player_id = %s
        order by season_id desc
        """,
        (player_id,),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Shortlist / talent mart queries
# ─────────────────────────────────────────────────────────────────────────────

def shortlist_leagues() -> list[str]:
    """Return distinct league_ids present in the shortlist mart."""
    frame = query(
        "select distinct league_id from mart.shortlist order by league_id"
    )
    return frame["league_id"].tolist() if not frame.empty else []


@st.cache_data(ttl=CACHE_TTL)
def shortlist_seasons() -> list[str]:
    frame = query(
        "select distinct season from mart.shortlist order by season desc"
    )
    return frame["season"].tolist() if not frame.empty else []


def shortlist_data(
    position_buckets: list[str] | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    min_minutes: int = 270,
    league_ids: list[str] | None = None,
    tiers: list[str] | None = None,
    min_talent_score: float = 0,
    seasons: list[str] | None = None,
    dob_confidences: list[str] | None = None,
) -> pd.DataFrame:
    """
    Query the mart.shortlist table with optional filters.
    Returns a DataFrame suitable for display and export.
    """
    conditions = ["minutes_played >= %s", "talent_score >= %s"]
    params: list = [min_minutes, min_talent_score]

    if position_buckets:
        placeholders = ",".join(["%s"] * len(position_buckets))
        conditions.append(f"position_bucket IN ({placeholders})")
        params.extend(position_buckets)

    if min_age is not None and max_age is not None:
        # Include players with NULL age (unknown DOB) so they're not silently hidden.
        conditions.append(
            "(age_at_midpoint IS NULL OR age_at_midpoint BETWEEN %s AND %s)"
        )
        params.extend([min_age, max_age])
    elif min_age is not None:
        conditions.append("(age_at_midpoint IS NULL OR age_at_midpoint >= %s)")
        params.append(min_age)
    elif max_age is not None:
        conditions.append("(age_at_midpoint IS NULL OR age_at_midpoint <= %s)")
        params.append(max_age)

    if league_ids:
        placeholders = ",".join(["%s"] * len(league_ids))
        conditions.append(f"league_id IN ({placeholders})")
        params.extend(league_ids)

    if tiers:
        placeholders = ",".join(["%s"] * len(tiers))
        conditions.append(f"data_tier IN ({placeholders})")
        params.extend(tiers)

    if seasons:
        placeholders = ",".join(["%s"] * len(seasons))
        conditions.append(f"season IN ({placeholders})")
        params.extend(seasons)

    if dob_confidences:
        placeholders = ",".join(["%s"] * len(dob_confidences))
        conditions.append(f"dob_confidence IN ({placeholders})")
        params.extend(dob_confidences)

    where = " AND ".join(conditions)
    sql = f"""
        select *
        from mart.shortlist
        where {where}
        order by talent_score desc nulls last
    """
    frame = query(sql, tuple(params))
    if frame.empty:
        return frame
    return frame.rename(
        columns={
            "age_at_midpoint": "age",
            "data_tier": "tier",
            "current_team_name": "club",
        }
    )


def shortlist_to_parquet(df: pd.DataFrame) -> bytes:
    """Serialise a shortlist DataFrame to Parquet bytes for download."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    return buffer.getvalue()


@st.cache_data(ttl=CACHE_TTL)
def coverage_summary() -> pd.DataFrame:
    """Coverage tier summary for all seasons."""
    return query(
        """
        select
            lsc.season_id,
            lsc.tier,
            lsc.pct_matches_with_result,
            lsc.pct_goals_with_scorer,
            lsc.pct_matches_with_lineups,
            lsc.pct_players_with_dob,
            lsc.computed_at
        from core.league_season_coverage lsc
        order by lsc.season_id
        """
    )


@st.cache_data(ttl=CACHE_TTL)
def conflict_summary() -> pd.DataFrame:
    """Recent multi-source disagreements."""
    return query(
        """
        select
            entity_type,
            entity_id,
            field,
            source_a_id,
            source_a_value,
            source_b_id,
            source_b_value,
            winning_source,
            logged_at
        from core.conflict_log
        order by logged_at desc
        limit 200
        """
    )
