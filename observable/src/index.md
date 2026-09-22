---
theme: dashboard
toc: false
---

# African Football Data

```js
import { talentHistogram, coverageChart, LEAGUE_LABELS } from "./components/charts.js";

const raw = await FileAttachment("data/overview.json").json();
const kpi      = raw.kpi      ?? {};
const coverage = raw.coverage ?? [];
const hist     = raw.histogram ?? [];
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Leagues</h2>
    <span class="big">${kpi.leagues ?? "—"}</span>
  </div>
  <div class="card">
    <h2>Matches</h2>
    <span class="big">${(+(kpi.matches ?? 0)).toLocaleString()}</span>
  </div>
  <div class="card">
    <h2>Players</h2>
    <span class="big">${(+(kpi.players ?? 0)).toLocaleString()}</span>
  </div>
  <div class="card">
    <h2>Avg talent score</h2>
    <span class="big">${kpi.avg_talent != null ? (+kpi.avg_talent).toFixed(1) : "—"}</span>
  </div>
</div>

```js
if (hist.length === 0) {
  display(html`<p class="muted">No shortlist data yet — run <code>dbt run --select mart.shortlist</code> first.</p>`);
} else {
  display(resize((width) => talentHistogram(hist, { width })));
}
```

---

## Coverage by league

```js
// Deduplicate: keep only the best (latest) tier per competition for overview bars
const latestCov = Object.values(
  Object.fromEntries(coverage.map((r) => [r.competition_id ?? r.league_id, r]))
);

if (latestCov.length === 0) {
  display(html`<p class="muted">No coverage data yet — run <code>dbt build</code> first.</p>`);
} else {
  display(resize((width) => coverageChart(latestCov, { width })));
}
```

---

<div class="grid grid-cols-2">
  <div class="card">
    <h3><a href="./league">📊 Leagues</a></h3>
    <p>Standings, points chart, attack vs defence, and all match results for each competition and season.</p>
  </div>
  <div class="card">
    <h3><a href="./shortlist">🔍 Scout Shortlist</a></h3>
    <p>Filter players from all Wave 1 leagues by position, minutes, talent score, and more.</p>
  </div>
  <div class="card">
    <h3><a href="./players">👤 Player Profiles</a></h3>
    <p>Photos, Wikipedia bios, career appearances, and per-season stats for individual players.</p>
  </div>
  <div class="card">
    <h3><a href="./coverage">📋 Coverage</a></h3>
    <p>Data-quality metrics by league-season: result %, scorer %, lineup %, DOB coverage.</p>
  </div>
</div>

<style>
.big { font-size: 2.4rem; font-weight: 700; letter-spacing: -0.03em; }
.muted { color: var(--theme-foreground-muted); }
</style>
