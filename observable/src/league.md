---
theme: dashboard
toc: false
---

# Leagues

```js
import {
  pointsChart, attackDefenceChart, outcomesChart, leagueLabel, LEAGUE_LABELS
} from "./components/charts.js";

const leaguesMeta   = await FileAttachment("data/leagues.json").json();
const allStandings  = await FileAttachment("data/standings.json").json();
const allMatches    = await FileAttachment("data/matches.json").json();
const allTotals     = await FileAttachment("data/season_totals.json").json();
```

```js
// Build league → seasons map
const leagueSeasons = new Map(
  leaguesMeta.map((l) => [l.competition_id, (l.seasons ?? []).filter(Boolean)])
);
const leagueIds  = leaguesMeta.map((l) => l.competition_id);
const leagueOpts = leagueIds.map((id) => ({ value: id, label: leagueLabel(id) }));
```

```js
const leagueInput = Inputs.select(leagueOpts, {
  label: "League",
  format: (d) => d.label,
  value: leagueOpts[0],
});
const selectedLeagueOpt = Generators.input(leagueInput);
display(leagueInput);
```

```js
const selectedLeague = selectedLeagueOpt?.value ?? leagueIds[0];
const seasons = leagueSeasons.get(selectedLeague) ?? [];
```

```js
const seasonInput = Inputs.select(seasons, { label: "Season" });
const selectedSeason = Generators.input(seasonInput);
display(seasons.length > 0 ? seasonInput : html`<p class="muted">No seasons available for this league.</p>`);
```

```js
const standings = allStandings.filter(
  (r) => r.league_id === selectedLeague && r.season === selectedSeason
);

const totals = allTotals.find(
  (r) => r.league_id === selectedLeague && r.season === selectedSeason
) ?? {};
```

---

```js
if (standings.length === 0) {
  display(html`<p class="muted">No data for <strong>${selectedSeason}</strong> — run the scrape and <code>dbt build</code> first.</p>`);
} else {
  const kpiMatches = +(totals.matches ?? 0);
  const kpiGoals   = +(totals.goals   ?? 0);
  const gpg        = kpiMatches > 0 ? (kpiGoals / kpiMatches).toFixed(2) : "—";
  const leader     = standings[0] ?? {};

  display(html`
    <div class="grid grid-cols-4">
      <div class="card"><h2>Matches</h2><span class="big">${kpiMatches}</span></div>
      <div class="card"><h2>Goals</h2><span class="big">${kpiGoals}</span></div>
      <div class="card"><h2>Goals / game</h2><span class="big">${gpg}</span></div>
      <div class="card"><h2>Leader pts</h2><span class="big">${leader.points ?? "—"}</span><p class="muted">${leader.team_name ?? ""}</p></div>
    </div>
  `);
}
```

## Standings

```js
if (standings.length > 0) {
  display(Inputs.table(standings, {
    columns: ["position","team_name","points","played","won","drawn","lost","goals_for","goals_against","goal_diff"],
    header:  { position:"Pos", team_name:"Club", points:"Pts", played:"P", won:"W", drawn:"D", lost:"L", goals_for:"GF", goals_against:"GA", goal_diff:"GD" },
    sort: "position",
    rows: 30,
  }));
}
```

## Charts

```js
if (standings.length > 0) {
  display(html`
    <div class="grid grid-cols-2">
      <div class="card">${resize((w) => pointsChart(standings, { width: w }))}</div>
      <div class="card">${resize((w) => attackDefenceChart(standings, { width: w }))}</div>
    </div>
    <div class="grid grid-cols-1">
      <div class="card">${resize((w) => outcomesChart(totals, { width: w }))}</div>
    </div>
  `);
}
```

## Matches

```js
const clubList = [...new Set(
  allMatches
    .filter((r) => r.league_id === selectedLeague && r.season === selectedSeason)
    .flatMap((r) => [r.home, r.away])
)].sort();

const clubInput = Inputs.select(["All clubs", ...clubList], { label: "Club filter" });
const clubFilter = Generators.input(clubInput);
display(clubInput);
```

```js
const matchRows = allMatches
  .filter((r) => r.league_id === selectedLeague && r.season === selectedSeason)
  .filter((r) => clubFilter === "All clubs" || r.home === clubFilter || r.away === clubFilter)
  .map((r) => ({
    date:  r.match_date ? r.match_date.slice(0, 10) : "—",
    home:  r.home,
    score: `${r.home_goals ?? "?"} – ${r.away_goals ?? "?"}`,
    away:  r.away,
  }));

if (matchRows.length === 0) {
  display(html`<p class="muted">No match data for this selection.</p>`);
} else {
  display(html`<p class="muted">${matchRows.length} matches</p>`);
  display(Inputs.table(matchRows, { rows: 50 }));
}
```

<style>
.big   { font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; }
.muted { color: var(--theme-foreground-muted); }
</style>
