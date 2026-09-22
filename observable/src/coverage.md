---
theme: dashboard
toc: false
---

# Data Coverage

```js
import { coverageChart } from "./components/charts.js";

const rows      = await FileAttachment("data/coverage.json").json();
const conflicts = await FileAttachment("data/conflicts.json").json();
```

**Tier A** = lineups + scorers + DOBs. **Tier B** = results + some scorers. **Tier C** = results only. Blank = below 70% match coverage.

```js
if (rows.length === 0) {
  display(html`<p class="muted">No coverage data yet — run <code>dbt build</code> first.</p>`);
} else {
  display(resize((width) => coverageChart(rows, { width })));
}
```

---

## Coverage table

```js
const TIER_ICON = { A: "🟢 A", B: "🟡 B", C: "🟠 C" };
const fmt = (v) => v != null ? `${(+v).toFixed(1)}%` : "—";

const display_rows = rows.map((r) => ({
  league:   r.league_name ?? r.competition_id,
  season_id: r.season_id,
  tier:     TIER_ICON[r.tier] ?? (r.tier ?? "—"),
  result:   fmt(r.pct_matches_with_result),
  scorer:   fmt(r.pct_goals_with_scorer),
  lineups:  fmt(r.pct_matches_with_lineups),
  dob:      fmt(r.pct_players_with_dob),
}));

display(Inputs.table(display_rows, {
  columns: ["league","season_id","tier","result","scorer","lineups","dob"],
  header: {
    league:    "League",
    season_id: "Season",
    tier:      "Tier",
    result:    "Match result%",
    scorer:    "Scorer known%",
    lineups:   "Lineups%",
    dob:       "DOB known%",
  },
  rows: 100,
}));
```

---

## Source conflicts

```js
if (conflicts.length === 0) {
  display(html`<p class="muted">No conflicts logged.</p>`);
} else {
  display(html`<p class="muted">${conflicts.length} recent conflict(s)</p>`);
  display(Inputs.table(conflicts, {
    columns: ["entity_type","entity_id","field","source_a_value","source_b_value","winning_source","logged_at"],
    header: {
      entity_type:   "Type",
      entity_id:     "ID",
      field:         "Field",
      source_a_value:"Value A",
      source_b_value:"Value B",
      winning_source:"Winner",
      logged_at:     "Logged",
    },
    rows: 50,
  }));
}
```

<style>
.muted { color: var(--theme-foreground-muted); }
</style>
