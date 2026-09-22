---
theme: dashboard
toc: false
---

# Scout Shortlist

```js
import { talentScatter, leagueLabel } from "./components/charts.js";

// Load as raw strings to prevent D3 autoType converting "2024-25" → Invalid Date.
// Numeric columns are coerced manually below.
const _rawStr = await FileAttachment("data/shortlist.csv").csv();

const _NUM_COLS = [
  "age", "height_cm", "talent_score", "gk_talent_score",
  "appearances", "starts", "minutes_played",
  "goals", "goals_per90", "assists", "assists_per90",
  "own_goals", "yellow_cards", "red_cards", "clean_sheets",
  "minutes_share", "starts_share",
  "goals_per90_pct_league", "minutes_share_pct_league",
  "goals_per90_pct_continental", "minutes_share_pct_continental",
  "prev_minutes_share", "prev_goals_per90", "minutes_share_delta", "goals_per90_delta",
  "career_appearances", "career_goals", "career_clubs", "career_goals_per_app",
  "conceded_p90", "expected_p90", "goals_prevented_p90", "clean_sheet_rate",
  "gk_conceded", "gk_expected", "gk_pct_minutes_share", "gk_pct_goals_prevented", "gk_pct_clean_sheets",
  "comp_minutes_share", "comp_output_per90", "comp_position_pct",
  "comp_age_factor", "comp_progression", "comp_league_strength",
];

const rawCsv = _rawStr.map(d => {
  const out = {...d};
  for (const col of _NUM_COLS) {
    if (col in out) out[col] = (out[col] === "" || out[col] == null) ? null : +out[col];
  }
  return out;
});
```

```js
if (rawCsv.length === 0) {
  display(html`<p class="muted">No shortlist data yet — run <code>dbt run --select mart.shortlist</code> then refresh.</p>`);
}
```

---

## Filters

```js
// ── Filter controls ────────────────────────────────────────────────────────
const nameInput = Inputs.search(rawCsv, {
  label: "Name search",
  placeholder: "e.g. Zwane",
  columns: ["full_name", "known_as"],
});
const nameFiltered = Generators.input(nameInput);
display(nameInput);
```

```js
const allLeagues   = [...new Set(rawCsv.map((d) => d.league_id).filter(Boolean))].sort();
const allPositions = [...new Set(rawCsv.map((d) => d.position_bucket).filter(Boolean))].sort();
const allTiers     = [...new Set(rawCsv.map((d) => d.tier).filter(Boolean))].sort();
const allSeasons   = [...new Set(rawCsv.map((d) => d.season).filter(Boolean))].sort().reverse();
```

```js
const posInput = Inputs.checkbox(allPositions, { label: "Position (empty = all)" });
const lgInput  = Inputs.checkbox(allLeagues,   {
  label: "League (empty = all)",
  format: leagueLabel,
});
const tierInput = Inputs.checkbox(allTiers, { label: "Tier (empty = all)" });

display(html`<div class="grid grid-cols-3">
  <div>${posInput}</div>
  <div>${lgInput}</div>
  <div>${tierInput}</div>
</div>`);

const posFilter  = Generators.input(posInput);
const lgFilter   = Generators.input(lgInput);
const tierFilter = Generators.input(tierInput);
```

```js
const seasonInput  = Inputs.checkbox(allSeasons, { label: "Season (empty = all)" });
const minMinsInput = Inputs.range([0, 3420], { value: 270, step: 90, label: "Min minutes" });
const minScoreInput = Inputs.range([0, 100], { value: 10, step: 1, label: "Min talent score" });

display(html`<div class="grid grid-cols-3">
  <div>${seasonInput}</div>
  <div>${minMinsInput}</div>
  <div>${minScoreInput}</div>
</div>`);

const seasonFilter  = Generators.input(seasonInput);
const minMins       = Generators.input(minMinsInput);
const minScore      = Generators.input(minScoreInput);
```

---

```js
// ── Apply filters ──────────────────────────────────────────────────────────
const df = nameFiltered.filter((d) => {
  if (posFilter.length  > 0 && !posFilter.includes(d.position_bucket)) return false;
  if (lgFilter.length   > 0 && !lgFilter.includes(d.league_id))        return false;
  if (tierFilter.length > 0 && !tierFilter.includes(d.tier))           return false;
  if (seasonFilter.length > 0 && !seasonFilter.includes(d.season))     return false;
  if ((d.minutes_played ?? 0) < minMins)   return false;
  if ((d.talent_score   ?? 0) < minScore)  return false;
  return true;
});

const hasGK = df.some((d) => d.position_bucket === "GK");
```

## ${df.length.toLocaleString()} players

```js
// KPI row
const avgScore = df.length > 0
  ? (df.reduce((s, d) => s + (d.talent_score ?? 0), 0) / df.length).toFixed(1)
  : "—";
const topScore = df.length > 0 ? Math.max(...df.map((d) => d.talent_score ?? 0)).toFixed(1) : "—";
const leagues  = new Set(df.map((d) => d.league_name)).size;

display(html`
  <div class="grid grid-cols-4">
    <div class="card"><h2>Players</h2><span class="big">${df.length}</span></div>
    <div class="card"><h2>Leagues</h2><span class="big">${leagues}</span></div>
    <div class="card"><h2>Avg score</h2><span class="big">${avgScore}</span></div>
    <div class="card"><h2>Top score</h2><span class="big">${topScore}</span></div>
  </div>
`);
```

```js
// Scatter plot
if (df.length > 0) {
  display(resize((width) => talentScatter(df, { width })));
}
```

## Scout table

```js
const tableColumns = hasGK
  ? ["full_name","position_bucket","age","talent_score","gk_talent_score","club","league_name","season","appearances","minutes_played","goals_prevented_p90","clean_sheet_rate"]
  : ["full_name","position_bucket","age","talent_score","club","league_name","season","appearances","minutes_played","goals","goals_per90"];

const tableHeader = {
  full_name:         "Name",
  position_bucket:   "Pos",
  age:               "Age",
  talent_score:      "Score",
  gk_talent_score:   "GK score",
  club:              "Club",
  league_name:       "League",
  season:            "Season",
  appearances:       "Apps",
  minutes_played:    "Mins",
  goals:             "G",
  goals_per90:       "G/90",
  goals_prevented_p90: "Prev/90",
  clean_sheet_rate:  "CS%",
};

if (df.length === 0) {
  display(html`<p class="muted">No players match the current filters.</p>`);
} else {
  display(Inputs.table(df, {
    columns: tableColumns.filter((c) => df[0] && c in df[0]),
    header:  tableHeader,
    rows: 50,
    sort: "talent_score",
    reverse: true,
    format: {
      talent_score:     (v) => v != null ? v.toFixed(1) : "—",
      gk_talent_score:  (v) => v != null ? v.toFixed(1) : "—",
      goals_per90:      (v) => v != null ? v.toFixed(2) : "—",
      goals_prevented_p90: (v) => v != null ? v.toFixed(2) : "—",
      clean_sheet_rate: (v) => v != null ? `${(v * 100).toFixed(0)}%` : "—",
      age:              (v) => v != null ? Math.floor(v) : "—",
    },
  }));
}
```

<style>
.big   { font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; }
.muted { color: var(--theme-foreground-muted); }
</style>
