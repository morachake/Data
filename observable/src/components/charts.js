/**
 * charts.js — shared Observable Plot helpers for the African Football Data dashboard.
 *
 * All chart functions return a Plot figure element and accept an optional
 * `{ width }` option so they compose with Framework's `resize()` helper.
 */

import * as Plot from "@observablehq/plot";

// ── Palette ───────────────────────────────────────────────────────────────────

export const GOLD   = "#d4a017";
export const GREEN  = "#3fa66b";
export const RED    = "#d45d4a";
export const MUTED  = "#8b98a5";
export const ACCENT = "#4e8cff";

// ── League labels ─────────────────────────────────────────────────────────────

export const LEAGUE_LABELS = {
  RSA_PREM:   "🇿🇦 SA Premiership",
  EGY_PL:     "🇪🇬 Egyptian PL",
  MAR_BOTOLA: "🇲🇦 Botola Pro",
  TZA_PL:     "🇹🇿 Tanzania PL",
  KEN_PL:     "🇰🇪 Kenyan PL",
  ALG_L1:     "🇩🇿 Algerian L1",
  TUN_L1:     "🇹🇳 Tunisian L1",
  NGA_NPFL:   "🇳🇬 Nigeria PFL",
  GHA_GPL:    "🇬🇭 Ghana PL",
  CIV_L1:     "🇨🇮 Ligue 1 CIV",
  CAF_CL:     "🌍 CAF CL",
  CAF_CC:     "🌍 CAF CC",
};

export function leagueLabel(id) {
  return LEAGUE_LABELS[id] ?? id;
}

// ── Points chart ──────────────────────────────────────────────────────────────

/**
 * Horizontal bar chart: teams ordered by points.
 * @param {Array}  rows  — standings rows with { team_name, points }
 * @param {object} opts  — { width? }
 */
export function pointsChart(rows, { width } = {}) {
  const sorted = [...rows].sort((a, b) => a.points - b.points);
  return Plot.plot({
    width,
    marginLeft: 150,
    title: "Points by club",
    x: { label: "Points", grid: true },
    y: { label: null },
    marks: [
      Plot.barX(sorted, {
        x: "points",
        y: "team_name",
        fill: GOLD,
        sort: { y: "x" },
        tip: true,
      }),
      Plot.ruleX([0]),
    ],
  });
}

// ── Attack vs defence ─────────────────────────────────────────────────────────

/**
 * Grouped horizontal bar chart: goals for vs goals against per club.
 * @param {Array}  rows  — standings rows with { team_name, goals_for, goals_against }
 * @param {object} opts  — { width? }
 */
export function attackDefenceChart(rows, { width } = {}) {
  // Pivot to long form expected by Plot
  const long = rows.flatMap((r) => [
    { team: r.team_name, metric: "Goals for",     value: r.goals_for      },
    { team: r.team_name, metric: "Goals against", value: r.goals_against  },
  ]).sort((a, b) => {
    // Order by goals_for descending
    const aRow = rows.find((r) => r.team_name === a.team);
    const bRow = rows.find((r) => r.team_name === b.team);
    return bRow.goals_for - aRow.goals_for;
  });

  const teams = [...new Set(long.map((d) => d.team))];

  return Plot.plot({
    width,
    marginLeft: 150,
    title: "Attack vs Defence",
    x: { label: "Goals", grid: true },
    y: { label: null, domain: teams },
    color: { domain: ["Goals for", "Goals against"], range: [GREEN, RED], legend: true },
    marks: [
      Plot.barX(long, {
        x: "value",
        y: "team",
        fill: "metric",
        tip: true,
      }),
      Plot.ruleX([0]),
    ],
  });
}

// ── Match outcomes donut ──────────────────────────────────────────────────────

/**
 * Pie / arc chart: home wins, draws, away wins.
 * Observable Plot doesn't have a native pie, so we use an arc from D3.
 * Falls back to a simple bar if totals row is missing.
 * @param {{ home_wins, draws, away_wins, matches }} totals
 * @param {object} opts — { width? }
 */
export function outcomesChart(totals, { width = 320 } = {}) {
  const data = [
    { label: "Home wins", value: +(totals?.home_wins ?? 0), color: GREEN  },
    { label: "Draws",     value: +(totals?.draws     ?? 0), color: MUTED  },
    { label: "Away wins", value: +(totals?.away_wins ?? 0), color: GOLD   },
  ];

  // Simple horizontal stacked bar (Plot-native, no D3 arc needed)
  return Plot.plot({
    width,
    height: 80,
    title: "Match outcomes",
    x: { label: null, tickFormat: "d" },
    y: { axis: null },
    color: {
      domain: data.map((d) => d.label),
      range:  data.map((d) => d.color),
      legend: true,
    },
    marks: [
      Plot.barX(data, {
        x: "value",
        fill: "label",
        tip: { format: { x: "d" } },
      }),
    ],
  });
}

// ── Talent scatter ────────────────────────────────────────────────────────────

/**
 * Scatter plot: minutes played × talent score.
 * @param {Array}  rows  — shortlist rows
 * @param {object} opts  — { width?, onSelect? }
 */
export function talentScatter(rows, { width } = {}) {
  return Plot.plot({
    width,
    title: "Talent score vs minutes played",
    x: { label: "Minutes played", grid: true },
    y: { label: "Talent score (0–100)", domain: [0, 100], grid: true },
    color: { scheme: "Viridis", label: "Score", legend: true },
    marks: [
      Plot.dot(rows, {
        x: "minutes_played",
        y: "talent_score",
        fill: "talent_score",
        r: 5,
        tip: {
          format: {
            x: ",.0f",
            y: ".1f",
          },
        },
        channels: { Name: "full_name", League: "league_name", Club: "club" },
      }),
    ],
  });
}

// ── Talent score histogram ────────────────────────────────────────────────────

/**
 * Histogram of talent scores (uses pre-computed buckets from loader).
 * @param {Array}  rows  — [{ bucket, count }]
 * @param {object} opts  — { width? }
 */
export function talentHistogram(rows, { width } = {}) {
  // bucket 1-20 → midpoint (bucket-0.5)*5
  const data = rows.map((r) => ({
    score:  (+(r.bucket ?? 0) - 0.5) * 5,
    count: +r.count,
  }));

  return Plot.plot({
    width,
    title: "Talent score distribution",
    x: { label: "Score (0–100)", domain: [0, 100] },
    y: { label: "Players", grid: true },
    marks: [
      Plot.rectY(data, {
        x1: (d) => d.score - 2.5,
        x2: (d) => d.score + 2.5,
        y:  "count",
        fill: ACCENT,
        tip: true,
      }),
      Plot.ruleY([0]),
    ],
  });
}

// ── Coverage bar chart ────────────────────────────────────────────────────────

/**
 * Horizontal grouped bars for coverage % metrics per league.
 * @param {Array}  rows  — coverage rows
 * @param {object} opts  — { width? }
 */
export function coverageChart(rows, { width } = {}) {
  const metrics = [
    { key: "pct_matches_with_result",  label: "Match result" },
    { key: "pct_goals_with_scorer",    label: "Scorer known" },
    { key: "pct_matches_with_lineups", label: "Lineups"      },
    { key: "pct_players_with_dob",     label: "DOB known"    },
  ];

  const long = rows.flatMap((r) =>
    metrics.map(({ key, label }) => ({
      league: r.league_name ?? r.competition_id ?? r.league_id,
      metric: label,
      value:  +(r[key] ?? 0),
    }))
  );

  return Plot.plot({
    width,
    marginLeft: 160,
    title: "Data coverage by league",
    x: { label: "Coverage %", domain: [0, 100], grid: true },
    y: { label: null },
    color: { legend: true },
    marks: [
      Plot.barX(long, {
        x: "value",
        y: "league",
        fill: "metric",
        tip: true,
      }),
      Plot.ruleX([0]),
    ],
  });
}
