import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from db import (
    matches,
    player_career,
    player_index,
    player_injuries,
    player_profile,
    player_season_stats,
    player_squad,
    season_totals,
    seasons,
    standings,
)

st.set_page_config(page_title="PSL Explorer", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
      header[data-testid="stHeader"] { background: transparent; }
      .block-container { padding-top: 2.2rem; padding-bottom: 2rem; }
      h1 { letter-spacing: -0.03em; }
      div[data-testid="stMetric"] {
        background: #1b2128;
        border: 1px solid #2a333c;
        padding: 0.7rem 0.9rem;
        border-radius: 8px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e7ece8", size=13),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(gridcolor="#2a333c", zeroline=False),
    yaxis=dict(gridcolor="#2a333c", zeroline=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)

GOLD = "#d4a017"
GREEN = "#3fa66b"
RED = "#d45d4a"
MUTED = "#8b98a5"


def format_standings(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["goal_diff"] = out["goal_diff"].map(lambda n: f"+{n}" if n > 0 else str(n))
    out = out.rename(
        columns={
            "position": "Pos",
            "team_name": "Club",
            "played": "P",
            "won": "W",
            "drawn": "D",
            "lost": "L",
            "goals_for": "GF",
            "goals_against": "GA",
            "goal_diff": "GD",
            "points": "Pts",
        }
    )
    return out[["Pos", "Club", "Pts", "P", "W", "D", "L", "GF", "GA", "GD"]]


def points_chart(frame: pd.DataFrame) -> go.Figure:
    ordered = frame.sort_values("points")
    fig = go.Figure(
        go.Bar(
            x=ordered["points"],
            y=ordered["team_name"],
            orientation="h",
            marker_color=GOLD,
            hovertemplate="%{y}<br>%{x} pts<extra></extra>",
        )
    )
    fig.update_layout(
        **CHART_LAYOUT,
        title="Points by club",
        xaxis_title="Points",
        yaxis_title="",
        height=max(420, 28 * len(ordered)),
    )
    return fig


def attack_defence_chart(frame: pd.DataFrame) -> go.Figure:
    ordered = frame.sort_values("goals_for")
    fig = go.Figure()
    fig.add_bar(
        name="Goals for",
        x=ordered["goals_for"],
        y=ordered["team_name"],
        orientation="h",
        marker_color=GREEN,
    )
    fig.add_bar(
        name="Goals against",
        x=ordered["goals_against"],
        y=ordered["team_name"],
        orientation="h",
        marker_color=RED,
    )
    fig.update_layout(
        **CHART_LAYOUT,
        barmode="group",
        title="Attack vs defence",
        xaxis_title="Goals",
        yaxis_title="",
        height=max(420, 28 * len(ordered)),
    )
    return fig


def results_chart(totals: pd.Series) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=["Home wins", "Draws", "Away wins"],
            values=[totals["home_wins"], totals["draws"], totals["away_wins"]],
            hole=0.62,
            marker=dict(colors=[GREEN, MUTED, GOLD]),
            textinfo="label+percent",
            hovertemplate="%{label}: %{value} matches<extra></extra>",
        )
    )
    fig.update_layout(**CHART_LAYOUT, title="Match outcomes", showlegend=False, height=360)
    return fig


available = seasons()
view = st.sidebar.radio("View", ["League", "Players"])

if view == "Players":
    index = player_index()
    if index.empty:
        st.title("Players")
        st.caption("No player profiles yet. Run `scrapy crawl wiki_psl_players` then load and dbt build.")
        st.stop()

    status = st.sidebar.selectbox("Status", ["All", "in_league", "left_league"])
    search = st.sidebar.text_input("Search name")
    filtered = index.copy()
    if status != "All":
        filtered = filtered[filtered["league_status"] == status]
    if search:
        filtered = filtered[filtered["full_name"].str.contains(search, case=False, na=False)]
    if filtered.empty:
        st.title("Players")
        st.caption("No players match that filter.")
        st.stop()

    labels = [
        f"{row.full_name} · {row.current_club or 'unattached'} · {row.league_status}"
        for row in filtered.itertuples()
    ]
    chosen = st.sidebar.selectbox("Player", labels)
    player_id = filtered.iloc[labels.index(chosen)]["player_id"]
    profile = player_profile(player_id).iloc[0]
    career = player_career(player_id)
    injuries = player_injuries(player_id)
    psl_stats = player_season_stats(profile["full_name"])
    squad = player_squad(profile["full_name"], profile["wiki_title"])

    photo, details = st.columns([1, 2], gap="large")
    with photo:
        if profile.get("image_url"):
            st.image(profile["image_url"], width=240)
        else:
            st.caption("No Wikipedia photo")
    with details:
        st.title(profile["full_name"])
        st.caption(profile.get("position") or "Position unknown")
        if profile.get("nationality"):
            st.caption(profile["nationality"])
        if profile.get("height"):
            st.caption(profile["height"])
        if profile.get("place_of_birth"):
            st.caption(profile["place_of_birth"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Current club", profile.get("current_club") or "—")
    c2.metric("Status", "In PSL" if profile["league_status"] == "in_league" else "Left PSL")
    c3.metric("Born", (profile.get("date_of_birth") or "—")[:32])

    if profile.get("bio"):
        st.subheader("Profile")
        st.write(profile["bio"])

    if not career.empty:
        st.subheader("Career appearances")
        st.dataframe(career, hide_index=True, width="stretch")

    if not squad.empty:
        st.subheader("PSL squads (2021–present)")
        st.dataframe(squad, hide_index=True, width="stretch")

    if not psl_stats.empty:
        st.subheader("PSL season leaders (2021–present)")
        st.dataframe(psl_stats, hide_index=True, width="stretch")

    st.subheader("Injuries and absences")
    if injuries.empty:
        st.caption("No injury notes found in the Wikipedia article.")
    else:
        for detail in injuries["detail"].tolist():
            st.write(detail)

    st.caption(profile.get("source_url") or "")
    st.stop()

if not available:
    st.error("No standings found. Run the scrape and `dbt build` first.")
    st.stop()

season = st.sidebar.selectbox("Season", available, index=0)
table = standings(season)
results = matches(season)
totals = season_totals(season).iloc[0]

st.title("South African Premiership")
st.caption(f"{season}  ·  Wikipedia results, rebuilt from match scores")

leader = table.iloc[0]
if int(leader["played"]) < 30:
    st.caption("Season in progress — table and charts update as more matches are scraped.")
kpi_matches = int(totals["matches"])
kpi_goals = int(totals["goals"] or 0)
kpi_gpg = kpi_goals / kpi_matches if kpi_matches else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Matches", kpi_matches)
c2.metric("Goals", kpi_goals)
c3.metric("Goals per game", f"{kpi_gpg:.2f}")
c4.metric("Leader pts", int(leader["points"]))
st.caption(f"Table-topper: {leader['team_name']}")

standings_tab, charts_tab, matches_tab = st.tabs(["Standings", "Charts", "Matches"])

with standings_tab:
    st.dataframe(
        format_standings(table),
        hide_index=True,
        width="stretch",
        height=560,
        column_config={
            "Pos": st.column_config.NumberColumn(width="small"),
            "Club": st.column_config.TextColumn(width="medium"),
            "Pts": st.column_config.NumberColumn(width="small"),
            "P": st.column_config.NumberColumn(width="small"),
            "W": st.column_config.NumberColumn(width="small"),
            "D": st.column_config.NumberColumn(width="small"),
            "L": st.column_config.NumberColumn(width="small"),
            "GF": st.column_config.NumberColumn(width="small"),
            "GA": st.column_config.NumberColumn(width="small"),
            "GD": st.column_config.TextColumn(width="small"),
        },
    )

with charts_tab:
    left, right = st.columns(2)
    with left:
        st.plotly_chart(points_chart(table), width="stretch")
        st.plotly_chart(results_chart(totals), width="stretch")
    with right:
        st.plotly_chart(attack_defence_chart(table), width="stretch")

with matches_tab:
    clubs = ["All clubs"] + sorted(set(results["home"]).union(results["away"]))
    club = st.selectbox("Filter by club", clubs)
    view = results.copy()
    if club != "All clubs":
        view = view[(view["home"] == club) | (view["away"] == club)]
    view["score"] = view["home_goals"].astype(str) + "–" + view["away_goals"].astype(str)
    display = view[["home", "score", "away"]].rename(
        columns={"home": "Home", "score": "Score", "away": "Away"}
    )
    st.caption(f"{len(display)} matches")
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=560,
        column_config={
            "Home": st.column_config.TextColumn(width="medium"),
            "Score": st.column_config.TextColumn(width="small"),
            "Away": st.column_config.TextColumn(width="medium"),
        },
    )
