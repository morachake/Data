import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)


def dsn() -> str:
    return (
        f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
        f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


def query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def seasons() -> list[str]:
    frame = query("select distinct season from core.standings order by season desc")
    return frame["season"].tolist()


def standings(season: str) -> pd.DataFrame:
    return query(
        """
        select
            s.position,
            t.team_name,
            s.played,
            s.won,
            s.drawn,
            s.lost,
            s.goals_for,
            s.goals_against,
            s.goal_diff,
            s.points
        from core.standings s
        join core.teams t on t.team_id = s.team_id
        where s.season = %s
        order by s.position
        """,
        (season,),
    )


def matches(season: str) -> pd.DataFrame:
    return query(
        """
        select
            h.team_name as home,
            a.team_name as away,
            m.home_goals,
            m.away_goals,
            m.result,
            m.source_url
        from core.fct_matches m
        join core.teams h on h.team_id = m.home_team_id
        join core.teams a on a.team_id = m.away_team_id
        where m.season = %s
        order by h.team_name, a.team_name
        """,
        (season,),
    )


def player_index() -> pd.DataFrame:
    return query(
        """
        select
            player_id,
            full_name,
            position,
            current_club,
            league_status,
            date_of_birth,
            image_url
        from core.dim_players
        order by full_name
        """
    )


def player_profile(player_id: str) -> pd.DataFrame:
    return query("select * from core.dim_players where player_id = %s", (player_id,))


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


def player_injuries(player_id: str) -> pd.DataFrame:
    return query(
        """
        select detail
        from core.fct_player_injuries
        where player_id = %s
        """,
        (player_id,),
    )


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
           or lower(wiki_title) = lower(%s)
        order by case when season = 'current' then 0 else 1 end, season desc
        """,
        (full_name, wiki_title),
    )


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


def season_totals(season: str) -> pd.DataFrame:
    return query(
        """
        select
            count(*) as matches,
            sum(home_goals + away_goals) as goals,
            sum((result = 'H')::int) as home_wins,
            sum((result = 'A')::int) as away_wins,
            sum((result = 'D')::int) as draws
        from core.fct_matches
        where season = %s
        """,
        (season,),
    )
