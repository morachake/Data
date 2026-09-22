---
theme: dashboard
toc: false
---

# Player Profiles

```js
// Load raw strings to avoid D3 autoType corrupting "2024-25" season strings
const _shortStr = await FileAttachment("data/shortlist.csv").csv();
const _SHORT_NUM = [
  "age","talent_score","gk_talent_score","appearances","starts","minutes_played",
  "goals","goals_per90","assists","assists_per90","clean_sheets",
  "conceded_p90","expected_p90","goals_prevented_p90","clean_sheet_rate",
];
const rawShort = _shortStr.map(d => {
  const out = {...d};
  for (const col of _SHORT_NUM) {
    if (col in out) out[col] = (out[col] === "" || out[col] == null) ? null : +out[col];
  }
  return out;
});

// career + squad come from the server; profile data is derived from rawShort
const rawExtra  = await FileAttachment("data/players.json").json();
const career    = rawExtra.career  ?? [];
const squad     = rawExtra.squad   ?? [];
```

```js
// Derive player profiles from the shortlist (de-duplicate to latest season per player)
// rawShort is sorted by talent_score DESC from the loader, so we just dedupe by player_id.
const _seen = new Set();
const profiles = rawShort
  .filter(d => d.player_id)
  .filter(d => { if (_seen.has(d.player_id)) return false; _seen.add(d.player_id); return true; })
  .sort((a, b) => (a.full_name ?? "").localeCompare(b.full_name ?? ""));
```

```js
if (profiles.length === 0) {
  display(html`<p class="muted">No player data yet — run the <code>wiki_psl_players</code> spider then <code>dbt build</code>.</p>`);
}
```

---

```js
// Name search
const searchInput = Inputs.text({ label: "Search name", placeholder: "e.g. Zwane, Francis…" });
const searchQuery = Generators.input(searchInput);
display(searchInput);
```

```js
const filtered = profiles.filter(p => {
  if (!searchQuery) return true;
  const q = searchQuery.toLowerCase();
  return (
    (p.full_name ?? "").toLowerCase().includes(q) ||
    (p.known_as  ?? "").toLowerCase().includes(q)
  );
});
```

```js
const playerInput = Inputs.select(filtered, {
  label: "Player",
  format: p => `${p.full_name ?? "—"} · ${p.club ?? "unattached"}`,
});
const selectedPlayer = Generators.input(playerInput);
display(
  filtered.length > 0
    ? playerInput
    : html`<p class="muted">No players match "${searchQuery}".</p>`
);
```

---

```js
if (selectedPlayer) {
  const p = selectedPlayer;
  const wikiTitle = p.known_as ?? p.full_name ?? "";
  const wikiUrl   = wikiTitle
    ? `https://en.wikipedia.org/wiki/${encodeURIComponent(wikiTitle.replace(/ /g, "_"))}`
    : null;
  const wdUrl = p.wikidata_id
    ? `https://www.wikidata.org/wiki/${p.wikidata_id}`
    : null;

  display(html`
    <div class="grid grid-cols-3" style="align-items:start">
      <div class="card" style="text-align:center">
        ${p.image_url
          ? html`<img src="${p.image_url}" style="max-width:200px;border-radius:8px" alt="${p.full_name}">`
          : html`<p class="muted" style="padding:2rem 0">No photo</p>`}
      </div>
      <div class="card grid-colspan-2">
        <h2 style="margin-top:0">${p.full_name ?? "—"}</h2>
        ${p.position_bucket ? html`<p><strong>Position:</strong> ${p.position ?? p.position_bucket}</p>` : ""}
        ${p.nationality     ? html`<p><strong>Nationality:</strong> ${p.nationality}</p>` : ""}
        ${p.height_cm       ? html`<p><strong>Height:</strong> ${p.height_cm} cm</p>` : ""}
        ${p.place_of_birth  ? html`<p>📍 ${p.place_of_birth}</p>` : ""}
        <p><strong>Current club:</strong> ${p.club ?? "—"}</p>
        <p>
          <strong>Date of birth:</strong>
          ${p.date_of_birth ? String(p.date_of_birth).slice(0,10) : "—"}
          ${p.dob_confidence ? html` <em class="muted">(${p.dob_confidence} confidence)</em>` : ""}
        </p>
        <div style="display:flex;gap:0.8rem;margin-top:0.6rem">
          ${wikiUrl ? html`<a href="${wikiUrl}" target="_blank" rel="noopener">🌐 Wikipedia</a>` : ""}
          ${wdUrl   ? html`<a href="${wdUrl}"   target="_blank" rel="noopener">📎 Wikidata</a>`  : ""}
        </div>
      </div>
    </div>
  `);

  // ── Season stats (from shortlist rows for this player) ──────────────────
  const pStats = rawShort.filter(r => r.player_id === p.player_id);
  if (pStats.length > 0) {
    const hasGK  = pStats.some(r => r.position_bucket === "GK");
    const statCols = hasGK
      ? ["league_name","season","club","appearances","minutes_played",
         "talent_score","gk_talent_score","goals_prevented_p90","clean_sheet_rate","tier"]
      : ["league_name","season","club","appearances","minutes_played",
         "goals","goals_per90","assists","talent_score","tier"];

    display(html`<h3>Season stats</h3>`);
    display(Inputs.table(pStats, {
      columns: statCols,
      header: {
        league_name:"League", season:"Season", club:"Club",
        appearances:"Apps", minutes_played:"Mins",
        goals:"G", goals_per90:"G/90", assists:"A",
        talent_score:"Score", gk_talent_score:"GK score",
        goals_prevented_p90:"Prev/90", clean_sheet_rate:"CS%", tier:"Tier",
      },
      format: {
        talent_score:        v => v != null ? (+v).toFixed(1) : "—",
        gk_talent_score:     v => v != null ? (+v).toFixed(1) : "—",
        goals_per90:         v => v != null ? (+v).toFixed(2) : "—",
        goals_prevented_p90: v => v != null ? (+v).toFixed(2) : "—",
        clean_sheet_rate:    v => v != null ? `${((+v)*100).toFixed(0)}%` : "—",
      },
      sort: "season",
      reverse: true,
      rows: 20,
    }));
  }

  // ── Career appearances ──────────────────────────────────────────────────
  const pCareer = career.filter(r => r.player_id === p.player_id);
  if (pCareer.length > 0) {
    display(html`<h3>Career appearances</h3>`);
    display(Inputs.table(pCareer, {
      columns: ["years","club","appearances","goals"],
      header:  { years:"Years", club:"Club", appearances:"Apps", goals:"G" },
    }));
  }

  // ── PSL squad history ───────────────────────────────────────────────────
  const pSquad = squad.filter(r => r.player_id === p.player_id);
  if (pSquad.length > 0) {
    display(html`<h3>Squad history</h3>`);
    display(Inputs.table(pSquad, {
      columns: ["season","club","position","shirt_no","appearances","goals"],
      header:  { season:"Season", club:"Club", position:"Pos", shirt_no:"#", appearances:"Apps", goals:"G" },
    }));
  }
}
```

<style>
.muted { color: var(--theme-foreground-muted); }
</style>
