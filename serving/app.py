"""
serving/app.py — African Football Data Platform dashboard.

Views: League | Players | Shortlist | Coverage

Navigation
----------
  st.query_params is the shareable source-of-truth:
    ?view=   League | Players | Shortlist | Coverage
    ?player= player_id  (opens a specific profile)
    ?league= competition_id  (pre-selects a league)
    ?season= season label    (pre-selects a season)
  goto(**params) sets those params and calls st.rerun().
  The sidebar radio is bound to st.session_state.nav_view which goto() updates.

Run:
    streamlit run serving/app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from db import (
    conflict_summary,
    coverage_summary,
    league_info,
    leagues,
    matches,
    player_career,
    player_index,
    player_injuries,
    player_profile,
    player_season_stats,
    player_shortlist_stats,
    player_squad,
    season_totals,
    seasons,
    shortlist_data,
    shortlist_seasons,
    shortlist_to_parquet,
    standings,
)
from filter_funnel import show_filter_funnel

CACHE_TTL = 300


@st.cache_data(ttl=CACHE_TTL)
def load_shortlist() -> pd.DataFrame:
    frame = shortlist_data(min_minutes=0, min_talent_score=0)
    if frame.empty:
        return frame
    out = frame.copy()
    for col in ("talent_score", "gk_talent_score"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").clip(lower=0, upper=100)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Navigation helper
# ─────────────────────────────────────────────────────────────────────────────

VIEW_OPTIONS = ["League", "Players", "Shortlist", "Coverage"]


def goto(**params: str) -> None:
    """Set query params and trigger a full rerun so row-clicks are shareable."""
    for k, v in params.items():
        st.query_params[k] = v
    if "view" in params and params["view"] in VIEW_OPTIONS:
        st.session_state.nav_view = params["view"]
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page config & global styles
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="African Football Data",
    layout="wide",
    initial_sidebar_state="expanded",
)

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


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

def format_standings(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["goal_diff"] = out["goal_diff"].map(lambda n: f"+{n}" if n > 0 else str(n))
    return out.rename(
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
    )[["Pos", "Club", "Pts", "P", "W", "D", "L", "GF", "GA", "GD"]]


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


def talent_scatter(df: pd.DataFrame) -> go.Figure:
    """Scatter of minutes × talent score; player_id packed in customdata for click-through."""
    fig = go.Figure(
        go.Scatter(
            x=df["minutes_played"],
            y=df["talent_score"],
            mode="markers",
            text=df["full_name"],
            customdata=df[["player_id"]].values,
            marker=dict(
                size=8,
                color=df["talent_score"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Score"),
            ),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Minutes: %{x}<br>"
                "Score: %{y:.1f}<br>"
                "<i>Click to open profile</i>"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **CHART_LAYOUT,
        title="Talent score vs minutes played  •  click a point to open profile",
        xaxis_title="Minutes played",
        yaxis_title="Talent score",
        height=460,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Session state bootstrap & sidebar navigation
# ─────────────────────────────────────────────────────────────────────────────

# Seed nav_view from ?view= on first load (makes shared URLs work)
if "nav_view" not in st.session_state:
    _qp_view = st.query_params.get("view", "League")
    st.session_state.nav_view = _qp_view if _qp_view in VIEW_OPTIONS else "League"

view = st.sidebar.radio(
    "View",
    VIEW_OPTIONS,
    index=VIEW_OPTIONS.index(st.session_state.nav_view),
)
# Keep session state in sync when the user clicks the radio directly
if view != st.session_state.nav_view:
    st.session_state.nav_view = view
    st.query_params["view"] = view


# ─────────────────────────────────────────────────────────────────────────────
# SHORTLIST TAB
# ─────────────────────────────────────────────────────────────────────────────

if view == "Shortlist":
    st.title("Scout Shortlist")
    st.caption(
        "Filter players from all Wave 1 leagues. "
        "Click a table row or chart point to open the full player profile."
    )

    st.info(
        "Leaderboard stats (goals, assists, clean sheets) are loaded for "
        "**all scraped leagues**. Full Wikipedia bios / DOB / photos are still "
        "richest for **RSA_PREM**. Age and nationality will be blank for most "
        "non-RSA players — use **Min minutes** and **Score** rather than age.",
        icon=None,
    )

    # Remove stale widget key that conflicts with session-state assignment
    if "shortlist_filters" in st.session_state:
        del st.session_state["shortlist_filters"]

    # ── Default filter state ─────────────────────────────────────────────────
    if "applied_shortlist" not in st.session_state:
        st.session_state.applied_shortlist = {
            "name": "",
            "positions": [],
            "age": (15, 35),
            "leagues": [],
            "tiers": [],
            "seasons": [],
            "min_minutes": 270,
            "min_score": 10,
            "dob": [],
            "latest_only": False,
        }

    f = st.session_state.applied_shortlist

    # ── Filter form ──────────────────────────────────────────────────────────
    with st.form("shortlist_filters_form"):
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            name_search = st.text_input(
                "Name search (contains, case-insensitive)",
                value=f["name"],
                placeholder="e.g. Zwane",
            )

            pos_options = ["GK", "DEF", "MID", "ATT", "FIELD"]
            selected_positions = st.multiselect(
                "Position",
                pos_options,
                default=f["positions"],
                help="Leave empty to include all positions",
            )

            age_min, age_max = st.slider(
                "Age range (players with unknown DOB are always included)",
                min_value=15,
                max_value=40,
                value=f["age"],
            )

        with col_b:
            all_leagues = leagues() or ["RSA_PREM"]
            selected_leagues = st.multiselect(
                "League",
                all_leagues,
                default=f["leagues"],
                help="Leave empty for all leagues",
            )

            selected_tiers = st.multiselect(
                "Data tier",
                ["A", "B", "C"],
                default=f["tiers"],
                help="A = full lineup data; B = results only; C = partial",
            )

            all_seasons = shortlist_seasons() or []
            selected_seasons = st.multiselect(
                "Season",
                all_seasons,
                default=f["seasons"],
                help="Leave empty for all seasons",
            )

        with col_c:
            min_minutes = st.number_input(
                "Min minutes played",
                min_value=0,
                max_value=3420,
                value=f["min_minutes"],
                step=90,
            )

            min_score = st.slider(
                "Min talent score",
                min_value=0,
                max_value=100,
                value=f["min_score"],
            )

            selected_dob = st.multiselect(
                "DOB confidence",
                ["high", "medium", "low", "unknown"],
                default=f["dob"],
            )

            latest_only = st.checkbox(
                "Latest season per player only",
                value=f["latest_only"],
                help=(
                    "Deduplicate to one row per player (their most recent season). "
                    "Removes repeat appearances from multi-season data."
                ),
            )

        apply_col, clear_col = st.columns([3, 1])
        with apply_col:
            applied = st.form_submit_button("Apply filters", type="primary")
        with clear_col:
            cleared = st.form_submit_button("Clear filters", type="secondary")

    if cleared:
        st.session_state.applied_shortlist = {
            "name": "",
            "positions": [],
            "age": (15, 35),
            "leagues": [],
            "tiers": [],
            "seasons": [],
            "min_minutes": 270,
            "min_score": 10,
            "dob": [],
            "latest_only": False,
        }
        st.rerun()

    if applied:
        st.session_state.applied_shortlist = {
            "name": name_search,
            "positions": selected_positions,
            "age": (age_min, age_max),
            "leagues": selected_leagues,
            "tiers": selected_tiers,
            "seasons": selected_seasons,
            "min_minutes": min_minutes,
            "min_score": min_score,
            "dob": selected_dob,
            "latest_only": latest_only,
        }

    f = st.session_state.applied_shortlist

    # ── Load full dataset (cached) ────────────────────────────────────────────
    raw = load_shortlist()

    if raw.empty:
        st.info(
            "No players in `mart.shortlist` yet — run `dbt run --select mart.shortlist`."
        )
        st.stop()

    # ── Build filter funnel ───────────────────────────────────────────────────
    filters: list[tuple[str, object]] = []

    if f["name"]:
        name_q = f["name"].lower()
        filters.append(
            (
                f'Name contains "{f["name"]}"',
                lambda d, q=name_q: (
                    d["full_name"].str.lower().str.contains(q, na=False)
                    | d["known_as"].str.lower().str.contains(q, na=False)
                ),
            )
        )
    if f["leagues"]:
        filters.append(
            ("League in selection", lambda d, sel=f["leagues"]: d["league_id"].isin(sel))
        )
    if f["tiers"]:
        filters.append(
            ("Data tier", lambda d, sel=f["tiers"]: d["tier"].isin(sel))
        )
    if f["positions"]:
        pos_label = ", ".join(f["positions"])
        filters.append(
            (
                f"Position in {pos_label}",
                lambda d, sel=f["positions"]: d["position_bucket"].isin(sel),
            )
        )
    if f["seasons"]:
        filters.append(
            ("Season in selection", lambda d, sel=f["seasons"]: d["season"].isin(sel))
        )
    age_lo, age_hi = f["age"]
    filters.append(
        (
            f"Age {age_lo}–{age_hi} or unknown",
            lambda d, lo=age_lo, hi=age_hi: d["age"].isna() | d["age"].between(lo, hi),
        )
    )
    filters.append(
        (f"Minutes ≥ {f['min_minutes']}", lambda d, m=f["min_minutes"]: d["minutes_played"] >= m)
    )
    filters.append(
        (f"Score ≥ {f['min_score']}", lambda d, s=f["min_score"]: d["talent_score"] >= s)
    )
    if f["dob"]:
        filters.append(
            ("DOB confidence", lambda d, sel=f["dob"]: d["dob_confidence"].isin(sel))
        )

    df = show_filter_funnel(raw, filters)
    if df is None:
        st.stop()

    # Deduplicate to latest season per player when requested
    if f["latest_only"] and "season_id" in df.columns:
        df = df.sort_values("season_id", ascending=False).drop_duplicates(subset="player_id")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    known_age = df["age"].notna().sum()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Players", len(df))
    k2.metric("Leagues", df["league_name"].nunique())
    k3.metric("Avg score", f"{df['talent_score'].mean():.1f}")
    k4.metric("Top score", f"{df['talent_score'].max():.1f}")
    k5.metric("Age known", f"{known_age}/{len(df)}", help="Players with a confirmed date of birth")

    # ── Scatter — click a point to open the profile ───────────────────────────
    scatter_df = df.reset_index(drop=True)
    scatter_event = st.plotly_chart(
        talent_scatter(scatter_df),
        width="stretch",
        on_select="rerun",
        selection_mode="points",
        key="scatter_sel",
    )
    try:
        pts = scatter_event.selection.points
        if pts:
            pid = str(pts[0].customdata[0])
            if pid and pid.lower() != "none":
                goto(view="Players", player=pid)
    except (AttributeError, IndexError, TypeError):
        pass

    # ── Default narrow scout table (click a row → profile) ───────────────────
    tbl = df.reset_index(drop=True).copy()

    # Construct Wikipedia URL from wiki_title (known_as)
    if "known_as" in tbl.columns:
        tbl["wiki_url"] = tbl["known_as"].map(
            lambda t: (
                f"https://en.wikipedia.org/wiki/{str(t).replace(' ', '_')}"
                if pd.notna(t)
                else None
            )
        )

    # Show GK extras when GK is in the position filter or GK rows are present
    show_gk = "GK" in f["positions"] or (
        "position_bucket" in tbl.columns and (tbl["position_bucket"] == "GK").any()
    )

    narrow_cols = [
        "image_url", "full_name", "position_bucket", "age",
        "talent_score", "club", "league_name", "season",
        "appearances", "minutes_played",
    ]
    if show_gk:
        narrow_cols += ["goals_prevented_p90", "clean_sheet_rate", "gk_talent_score"]
    else:
        narrow_cols += ["goals", "goals_per90"]

    narrow_display = (
        tbl[[c for c in narrow_cols if c in tbl.columns]]
        .rename(
            columns={
                "image_url": "Photo",
                "full_name": "Name",
                "position_bucket": "Pos",
                "age": "Age",
                "talent_score": "Score",
                "club": "Club",
                "league_name": "League",
                "season": "Season",
                "appearances": "Apps",
                "minutes_played": "Mins",
                "goals": "G",
                "goals_per90": "G/90",
                "goals_prevented_p90": "Prev/90",
                "clean_sheet_rate": "CS%",
                "gk_talent_score": "GK score",
            }
        )
        .copy()
    )
    if "Age" in narrow_display.columns:
        narrow_display["Age"] = narrow_display["Age"].astype("Int64")
    if "Club" in narrow_display.columns:
        narrow_display["Club"] = narrow_display["Club"].fillna("—")

    narrow_col_cfg: dict = {
        "Photo": st.column_config.ImageColumn("Photo", width="small"),
        "Score": st.column_config.NumberColumn(format="%.1f"),
        "G/90": st.column_config.NumberColumn(format="%.2f"),
        "Prev/90": st.column_config.NumberColumn(format="%.2f"),
        "CS%": st.column_config.NumberColumn(format="%.0%"),
        "GK score": st.column_config.NumberColumn(format="%.1f"),
    }

    st.caption("Click a row to open the full player profile.")
    tbl_event = st.dataframe(
        narrow_display,
        hide_index=True,
        width="stretch",
        height=520,
        column_config=narrow_col_cfg,
        on_select="rerun",
        selection_mode="single-row",
        key="shortlist_tbl",
    )
    try:
        if tbl_event.selection.rows:
            row_idx = tbl_event.selection.rows[0]
            pid = str(tbl.iloc[row_idx]["player_id"])
            goto(view="Players", player=pid)
    except (AttributeError, IndexError, TypeError):
        pass

    # ── Show all stats expander ───────────────────────────────────────────────
    with st.expander("Show all stats"):
        preferred_order = [
            "image_url", "full_name", "known_as", "position_bucket", "position",
            "age", "date_of_birth", "dob_confidence", "nationality", "height_cm",
            "place_of_birth", "club", "league_name", "season", "tier", "talent_score",
            "appearances", "starts", "minutes_played", "minutes_share", "starts_share",
            "goals", "goals_per90", "assists", "assists_per90", "own_goals",
            "yellow_cards", "red_cards", "clean_sheets",
            "comp_minutes_share", "comp_output_per90", "comp_position_pct",
            "comp_age_factor", "comp_progression", "comp_league_strength",
            "goals_per90_pct_league", "minutes_share_pct_league",
            "goals_per90_pct_continental", "minutes_share_pct_continental",
            "prev_minutes_share", "prev_goals_per90", "minutes_share_delta", "goals_per90_delta",
            "career_appearances", "career_goals", "career_goals_per_app", "career_clubs",
            "injury_notes",
            "conceded_p90", "expected_p90", "goals_prevented_p90", "clean_sheet_rate",
            "gk_talent_score", "gk_sample_confidence", "gk_conceded", "gk_expected",
            "gk_age_band", "gk_pct_minutes_share", "gk_pct_goals_prevented", "gk_pct_clean_sheets",
            "wikidata_id", "wiki_url",
        ]
        hidden_ids = {"player_id", "season_id", "current_team_id", "league_id"}
        wide_cols = [c for c in preferred_order if c in tbl.columns]
        wide_cols += [c for c in tbl.columns if c not in wide_cols and c not in hidden_ids]
        all_display = tbl[wide_cols].copy()
        if "age" in all_display.columns:
            all_display["age"] = all_display["age"].astype("Int64")
        if "nationality" in all_display.columns:
            all_display["nationality"] = all_display["nationality"].fillna("—")
        if "club" in all_display.columns:
            all_display["club"] = all_display["club"].fillna("—")

        all_display = all_display.rename(
            columns={
                "image_url": "Photo", "full_name": "Name", "known_as": "Known as",
                "position_bucket": "Pos", "position": "Position",
                "age": "Age", "date_of_birth": "DOB", "dob_confidence": "DOB?",
                "nationality": "Nat", "height_cm": "Ht", "place_of_birth": "Born",
                "club": "Club", "league_name": "League", "season": "Season",
                "tier": "Tier", "talent_score": "Score",
                "appearances": "Apps", "starts": "Starts",
                "minutes_played": "Mins", "minutes_share": "Min%", "starts_share": "Start%",
                "goals": "G", "goals_per90": "G/90",
                "assists": "A", "assists_per90": "A/90",
                "own_goals": "OG", "yellow_cards": "YC", "red_cards": "RC",
                "clean_sheets": "CS",
                "comp_minutes_share": "Comp min", "comp_output_per90": "Comp out",
                "comp_position_pct": "Comp pos", "comp_age_factor": "Comp age",
                "comp_progression": "Comp prog", "comp_league_strength": "Comp lg",
                "goals_per90_pct_league": "G/90 %lg", "minutes_share_pct_league": "Min %lg",
                "goals_per90_pct_continental": "G/90 %AF",
                "minutes_share_pct_continental": "Min %AF",
                "prev_minutes_share": "Prev min%", "prev_goals_per90": "Prev G/90",
                "minutes_share_delta": "Δ min%", "goals_per90_delta": "Δ G/90",
                "career_appearances": "Car apps", "career_goals": "Car G",
                "career_goals_per_app": "Car G/app", "career_clubs": "Clubs",
                "injury_notes": "Inj",
                "conceded_p90": "GA/90", "expected_p90": "xGA/90",
                "goals_prevented_p90": "Prev/90", "clean_sheet_rate": "CS%",
                "gk_talent_score": "GK score", "gk_sample_confidence": "GK sample",
                "gk_conceded": "GA", "gk_expected": "xGA", "gk_age_band": "GK age",
                "gk_pct_minutes_share": "GK min pct",
                "gk_pct_goals_prevented": "GK prev pct",
                "gk_pct_clean_sheets": "GK CS pct",
                "wikidata_id": "Wikidata", "wiki_url": "Wikipedia",
            }
        )
        wide_col_cfg: dict = {
            "Photo": st.column_config.ImageColumn("Photo", width="small"),
            "Score": st.column_config.NumberColumn(format="%.1f"),
            "G/90": st.column_config.NumberColumn(format="%.2f"),
            "A/90": st.column_config.NumberColumn(format="%.2f"),
            "Min%": st.column_config.NumberColumn(format="%.1f"),
            "Start%": st.column_config.NumberColumn(format="%.1f"),
            "GA/90": st.column_config.NumberColumn(format="%.2f"),
            "xGA/90": st.column_config.NumberColumn(format="%.2f"),
            "Prev/90": st.column_config.NumberColumn(format="%.2f"),
            "CS%": st.column_config.NumberColumn(format="%.0%"),
            "Car G/app": st.column_config.NumberColumn(format="%.2f"),
            "GK score": st.column_config.NumberColumn(format="%.1f"),
            "Wikipedia": st.column_config.LinkColumn("Wikipedia"),
        }
        st.dataframe(
            all_display,
            hide_index=True,
            width="stretch",
            height=520,
            column_config=wide_col_cfg,
        )

    # ── Parquet export ────────────────────────────────────────────────────────
    st.download_button(
        label="⬇  Download as Parquet",
        data=shortlist_to_parquet(df),
        file_name="shortlist.parquet",
        mime="application/octet-stream",
    )
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# COVERAGE TAB
# ─────────────────────────────────────────────────────────────────────────────

if view == "Coverage":
    st.title("Data Quality Coverage")
    st.caption(
        "Tier A = lineups + scorers + DOBs.  "
        "Tier B = results + some scorers.  "
        "Tier C = results only.  "
        "Blank = below 70% match coverage.  "
        "**Click a row** to open that league-season."
    )

    cov = coverage_summary()
    if cov.empty:
        st.info("No coverage data yet — run `dbt build` first.")
        st.stop()

    _TIER_EMOJI = {"A": "🟢 A", "B": "🟡 B", "C": "🟠 C"}

    def pct_label(value) -> str:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value):.1f}%"

    cov_display = cov.reset_index(drop=True).copy()
    # Emoji-prefix tier for scannable colour coding (works without Styler)
    if "tier" in cov_display.columns:
        cov_display["tier"] = cov_display["tier"].map(
            lambda t: _TIER_EMOJI.get(str(t), str(t) if pd.notna(t) else "—")
        )
    for col in ("pct_matches_with_result", "pct_goals_with_scorer",
                "pct_matches_with_lineups", "pct_players_with_dob"):
        if col in cov_display.columns:
            cov_display[col] = cov_display[col].apply(pct_label)

    cov_event = st.dataframe(
        cov_display,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="coverage_tbl",
    )

    try:
        if cov_event.selection.rows:
            row_idx = cov_event.selection.rows[0]
            season_id = str(cov.iloc[row_idx]["season_id"])
            # season_id = "RSA_PREM_2025–26" — split at the last _ before a digit
            split_at = None
            for i, ch in enumerate(season_id):
                if ch == "_" and i + 1 < len(season_id) and season_id[i + 1].isdigit():
                    split_at = i
            if split_at is not None:
                league_id = season_id[:split_at]
                season_label = season_id[split_at + 1:]
                goto(view="League", league=league_id, season=season_label)
    except (AttributeError, IndexError, TypeError):
        pass

    conflicts = conflict_summary()
    if not conflicts.empty:
        with st.expander(f"Source conflicts ({len(conflicts)} recent)"):
            st.dataframe(conflicts, hide_index=True, width="stretch")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# PLAYERS TAB
# ─────────────────────────────────────────────────────────────────────────────

if view == "Players":
    # Back button — returns to Shortlist (or previous view if set)
    if st.button("← Back to Shortlist"):
        goto(view="Shortlist")

    index = player_index()
    if index.empty:
        st.title("Players")
        st.caption(
            "No player profiles yet. "
            "Run `scrapy crawl wiki_psl_players` then load and `dbt build`."
        )
        st.stop()

    # Pre-fill search / selection from ?player= query param
    qp_player = st.query_params.get("player", "")

    search = st.sidebar.text_input("Search name")
    filtered = index.copy()
    if search:
        filtered = filtered[filtered["full_name"].str.contains(search, case=False, na=False)]

    if filtered.empty:
        st.title("Players")
        st.caption("No players match that filter.")
        st.stop()

    labels = [
        f"{row.full_name} · {row.current_club or 'unattached'}"
        for row in filtered.itertuples()
    ]

    # Find default selectbox index from ?player= param
    player_ids_list = filtered["player_id"].tolist()
    default_player_idx = (
        player_ids_list.index(qp_player) if qp_player in player_ids_list else 0
    )

    chosen = st.sidebar.selectbox("Player", labels, index=default_player_idx)
    player_id = filtered.iloc[labels.index(chosen)]["player_id"]
    # current_club from player_index() (shortlist join) is more up-to-date than Wikipedia
    index_current_club: str = filtered.iloc[labels.index(chosen)].get("current_club", "") or ""

    # Keep ?player= up to date while browsing
    st.query_params["player"] = player_id

    profile_rows = player_profile(player_id)
    if profile_rows.empty:
        st.warning("No profile found for this player.")
        st.stop()
    profile = profile_rows.iloc[0]

    shortlist_stats = player_shortlist_stats(player_id)
    career = player_career(player_id)
    injuries = player_injuries(player_id)
    psl_stats = player_season_stats(profile.get("full_name", ""))
    squad = player_squad(
        profile.get("full_name", ""),
        profile.get("known_as", profile.get("full_name", "")),
    )

    # ── Profile header ────────────────────────────────────────────────────────
    photo_col, details_col = st.columns([1, 2], gap="large")
    with photo_col:
        if profile.get("image_url"):
            st.image(profile["image_url"], width=240)
        else:
            st.caption("No Wikipedia photo")

    with details_col:
        st.title(profile.get("full_name", "Unknown"))
        if profile.get("position"):
            st.caption(profile["position"])
        if profile.get("nationality"):
            st.caption(profile["nationality"])
        if profile.get("height_cm"):
            st.caption(f"{profile['height_cm']} cm")
        if profile.get("place_of_birth"):
            st.caption(profile["place_of_birth"])

        # External links
        link_l, link_r = st.columns(2)
        wiki_title = profile.get("known_as") or profile.get("full_name")
        if wiki_title:
            wiki_url = f"https://en.wikipedia.org/wiki/{str(wiki_title).replace(' ', '_')}"
            link_l.link_button("🌐 Wikipedia", wiki_url)
        if profile.get("wikidata_id"):
            link_r.link_button(
                "📎 Wikidata",
                f"https://www.wikidata.org/wiki/{profile['wikidata_id']}",
            )

    c1, c2, c3 = st.columns(3)
    # Prefer shortlist-derived club (more current) over Wikipedia's current_club_raw
    _club_display = (
        index_current_club
        or profile.get("current_club_raw")
        or "—"
    )
    c1.metric("Current club", _club_display)
    c2.metric("DOB confidence", profile.get("dob_confidence", "unknown"))
    c3.metric("Born", str(profile.get("date_of_birth") or "—")[:10])

    # ── Shortlist season stats (primary scout data) ───────────────────────────
    if not shortlist_stats.empty:
        st.subheader("Season stats")
        ss = shortlist_stats.copy()
        for col in ("talent_score", "gk_talent_score"):
            if col in ss.columns:
                ss[col] = pd.to_numeric(ss[col], errors="coerce").clip(lower=0, upper=100)
        st.dataframe(
            ss,
            hide_index=True,
            width="stretch",
            column_config={
                "talent_score": st.column_config.NumberColumn("Score", format="%.1f"),
                "gk_talent_score": st.column_config.NumberColumn("GK score", format="%.1f"),
                "goals_per90": st.column_config.NumberColumn("G/90", format="%.2f"),
                "goals_prevented_p90": st.column_config.NumberColumn("Prev/90", format="%.2f"),
                "clean_sheet_rate": st.column_config.NumberColumn("CS%", format="%.0%"),
            },
        )

    if not career.empty:
        st.subheader("Career appearances")
        st.dataframe(career, hide_index=True, width="stretch")

    if not squad.empty:
        st.subheader("PSL squads (2021–present)")
        st.dataframe(squad, hide_index=True, width="stretch")

    if not psl_stats.empty:
        st.subheader("PSL season stats (leaderboard)")
        st.dataframe(psl_stats, hide_index=True, width="stretch")

    st.subheader("Injuries and absences")
    if injuries.empty:
        st.caption("No injury notes found.")
    else:
        for detail in injuries["detail"].tolist():
            st.write(detail)

    if profile.get("source_url"):
        st.caption(profile["source_url"])
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# LEAGUE TAB (default)
# ─────────────────────────────────────────────────────────────────────────────

all_leagues = leagues()
if not all_leagues:
    st.error("No league data found. Run the scrape and `dbt build` first.")
    st.stop()

_LEAGUE_LABELS = {
    "RSA_PREM":   "🇿🇦 SA Premiership",
    "EGY_PL":     "🇪🇬 Egyptian PL",
    "MAR_BOTOLA": "🇲🇦 Botola Pro",
    "TZA_PL":     "🇹🇿 Tanzania PL",
    "KEN_PL":     "🇰🇪 Kenyan PL",
    "ALG_L1":     "🇩🇿 Algerian L1",
    "TUN_L1":     "🇹🇳 Tunisian L1",
    "NGA_NPFL":   "🇳🇬 Nigeria PFL",
    "GHA_GPL":    "🇬🇭 Ghana PL",
    "CIV_L1":     "🇨🇮 Ligue 1 CIV",
    "CAF_CL":     "🌍 CAF CL",
    "CAF_CC":     "🌍 CAF CC",
}

# Read ?league= and ?season= written by Coverage row-click
_qp_league = st.query_params.get("league", "")
_qp_season = st.query_params.get("season", "")

league_default_idx = 0
if _qp_league and _qp_league in all_leagues:
    league_default_idx = all_leagues.index(_qp_league)

selected_league = st.sidebar.selectbox(
    "League",
    all_leagues,
    index=league_default_idx,
    format_func=lambda lid: _LEAGUE_LABELS.get(lid, lid),
)

comp = league_info(selected_league)
comp_name = comp.get("name", selected_league)

# ── Season selector ───────────────────────────────────────────────────────────
available = seasons(selected_league)
if not available:
    st.title(comp_name)
    st.info(
        f"No match data yet for **{comp_name}**. "
        "The JSONL files have been scraped — run `python loaders/load_jsonl.py` "
        "followed by `dbt build` to load them."
    )
    st.stop()

season_default_idx = 0
if _qp_season and _qp_season in available:
    season_default_idx = available.index(_qp_season)

season = st.sidebar.selectbox("Season", available, index=season_default_idx)

table = standings(season, selected_league)
results = matches(season, selected_league)
totals = season_totals(season, selected_league)

if totals.empty:
    st.error(f"No data for season {season}.")
    st.stop()

totals_row = totals.iloc[0]

st.title(comp_name)
st.caption(f"{season}  ·  Wikipedia + RSSSF results, rebuilt from match scores")

if not table.empty:
    leader = table.iloc[0]
    if int(leader["played"]) < 30:
        st.caption("Season in progress — table updates as more matches are scraped.")
    kpi_matches = int(totals_row["matches"])
    kpi_goals = int(totals_row["goals"] or 0)
    kpi_gpg = kpi_goals / kpi_matches if kpi_matches else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matches", kpi_matches)
    c2.metric("Goals", kpi_goals)
    c3.metric("Goals per game", f"{kpi_gpg:.2f}")
    c4.metric("Leader pts", int(leader["points"]))
    st.caption(f"Table-topper: {leader['team_name']}")

# Banner when a club was selected from standings
_preset_club = st.session_state.get("league_club_preset", "")
if _preset_club:
    st.info(
        f"📌 Showing results for **{_preset_club}** — click the **Matches** tab below.",
        icon=None,
    )

standings_tab, charts_tab, matches_tab = st.tabs(["Standings", "Charts", "Matches"])

with standings_tab:
    if not table.empty:
        st_table = format_standings(table).reset_index(drop=True)
        st.caption("Click a row to pre-filter the Matches tab for that club.")
        st_event = st.dataframe(
            st_table,
            hide_index=True,
            width="stretch",
            height=560,
            column_config={
                "Pos": st.column_config.NumberColumn(width="small"),
                "Club": st.column_config.TextColumn(width="medium"),
                "Pts": st.column_config.NumberColumn(width="small"),
            },
            on_select="rerun",
            selection_mode="single-row",
            key="standings_tbl",
        )
        try:
            if st_event.selection.rows:
                row_idx = st_event.selection.rows[0]
                club_name = str(st_table.iloc[row_idx]["Club"])
                st.session_state.league_club_preset = club_name
                st.rerun()
        except (AttributeError, IndexError, TypeError):
            pass
    else:
        st.caption("No standings data for this season.")

with charts_tab:
    if not table.empty:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(points_chart(table), width="stretch")
            st.plotly_chart(results_chart(totals_row), width="stretch")
        with right:
            st.plotly_chart(attack_defence_chart(table), width="stretch")

with matches_tab:
    if not results.empty:
        clubs = ["All clubs"] + sorted(set(results["home"]).union(results["away"]))
        preset = st.session_state.get("league_club_preset", "All clubs")
        club_idx = clubs.index(preset) if preset in clubs else 0
        club = st.selectbox("Filter by club", clubs, index=club_idx, key="club_filter_sel")
        view_df = results.copy()
        if club != "All clubs":
            view_df = view_df[(view_df["home"] == club) | (view_df["away"] == club)]
        view_df["score"] = (
            view_df["home_goals"].astype(str) + "–" + view_df["away_goals"].astype(str)
        )
        display = view_df[["home", "score", "away"]].rename(
            columns={"home": "Home", "score": "Score", "away": "Away"}
        )
        st.caption(f"{len(display)} matches")
        st.dataframe(display, hide_index=True, width="stretch", height=560)
    else:
        st.caption("No match data for this season.")
