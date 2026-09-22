# PSL Scrape Source Feasibility

Checked 2026-09-21 against each site's `robots.txt` and published Terms of Use.
Re-check before adding a new spider. Project rule: `ROBOTSTXT_OBEY = True`.

---

## Possible

| Site | URL | What we can collect | robots.txt | ToS | Status |
|------|-----|---------------------|------------|-----|--------|
| **Wikipedia** | `en.wikipedia.org/wiki/*` | Season tables, results matrices, player bios | `Allow: /wiki/` article paths; only `Special:` pages blocked | CC BY-SA — open re-use with attribution | **Already scraping** (`wiki_psl_seasons`, `wiki_psl_players`) |
| **Wikidata** | `www.wikidata.org` | Stable entity IDs for players and clubs | Same Wikimedia bot policy as Wikipedia | CC0 | Partially used (player spider stores `wikidata_id`) |
| **PSL official** | `psl.co.za/matchcentre` | Current-season fixtures, results, live logs, standings | `Allow: /` (no disallows for match pages) | Non-commercial personal/educational licence only. Commercial reuse needs written PSL consent. | **Next spider** (week-3 checklist) |
| **SuperSport** | `supersport.com` | News articles, fixture articles | `Allow: /`; **disallows `/api/*` and `/apix/*`** | Standard news ToU — HTML pages only, no API | Low priority; news filler |
| **KickOff** | `kickoff.com` | News, fixture summaries | Most paths allowed; blocks `/comments/`, `/search*`, `/user/*` | Forbids AI training (`ai-train=no`), but allows search/citation/reference use | Low priority; news filler |
| **Goal.com** | `goal.com/en-za/*` | News, match reports | `Allow: /` | Standard editorial ToU | Low priority; no structured history |
| **ESPN Soccer** | `espn.com/soccer/` | Scoreboard, some standings | Most soccer paths allowed, **not** `/soccer/matchstats`, `/soccer/lineups`, `/soccer/commentary`, `*/boxscore?` | Blocks AI crawlers (GPTBot, anthropic-ai). Weak PSL coverage | Last resort only |

---

## Not possible — do not add spiders

| Site | Reason |
|------|--------|
| **Transfermarkt** | `robots.txt` says `Allow: /` but **Terms §11.1 explicitly forbid bots, spiders, and screen scraping** (also AI training). ToS overrides the open robots file. |
| **Flashscore** | `Disallow: /standings/` and `/draw/`. ToS (Livesport s.r.o.) forbids copying or redistribution without prior written authorisation. No public API or licensing portal. |
| **Soccerway** | Same Livesport/Perform platform as Flashscore — identical robots block on `/standings/` and identical data-licensing restrictions. |
| **SofaScore** | `Disallow: /standings/` and all season paths `/*/2017-` through `/*/2025-`. No public API; data licensed from Opta/Perform — FAQ explicitly says they cannot share API endpoints. |
| **FBref / Sports-Reference** | ToS forbid automated access that harms performance; FBref rate-limits at >10 req/min and jails violators for up to a day. Underlying stats licensed from third parties; no redistribution allowed. |
| **WhoScored** | Terms explicitly prohibit copying, downloading, or republishing any stats, data, or tables without an official licence (Opta-backed). |
| **FotMob API** | `Disallow: /api/*` in `robots.txt`. The entire UI is SPA-driven; HTML pages without the API are empty. |
| **SuperSport API** | `Disallow: /api/*` and `/apix/*` in `robots.txt`. Same SPA issue as FotMob. |
| **CAF Online** | `robots.txt` returns 404 — no policy published. Unclear ToS. Not a PSL stats source anyway. |
| **PSL in-stadium / live feeds** | PSL ticket terms forbid collecting, transmitting, or distributing match data or statistics for anything other than personal use. |

---

## Project implication

1. **Keep Wikipedia** as the primary historical source (5+ completed seasons).
2. **Next spider: `psl_matchcentre`** for the current running season, to reconcile with Wikipedia results. Use the non-commercial licence; do not republish raw data.
3. **Do not build spiders for** Transfermarkt, Flashscore, Soccerway, SofaScore, FBref, or WhoScored — all blocked by ToS, robots, or both.
4. SuperSport / KickOff / Goal.com are only useful for news enrichment, not structured match data.

---

## Enrichment data sources — what they provide and how to integrate

The table below covers every enrichment dimension that would improve the Scout Shortlist and player dashboards: nationalities, market values, injury/suspension records, and advanced stats cards.

> **Key rule:** preferred approach is **official licensed APIs** or **open datasets** (Wikipedia/Wikidata/OpenFootball). Never scrape a site whose ToS or `robots.txt` forbids it — check the "Not possible" table above before adding a new source.

### ① Nationalities

| Source | Access method | Licence | What we get |
|--------|--------------|---------|-------------|
| **Wikipedia player infobox** | `wiki_psl_players` spider already extracts `nationality` | CC BY-SA | Nationality string; can be multi-value (e.g. "South African / Zimbabwean") |
| **Wikidata** (`P27` — country of citizenship) | SPARQL query via `https://query.wikidata.org/sparql` — no scraping ban, open API | CC0 | ISO country code, allow multi-nationality, stable across renames |
| **OpenFootball** (GitHub data dump) | `git clone https://github.com/openfootball/` — flat-file CSV/JSON | Public domain | Club rosters for top African leagues; nationalities per player |

**Integration plan:**
- Run a Wikidata SPARQL query per `player_id` (using the `wikidata_id` column already stored in `core.player`) to backfill `nationality` for players where Wikipedia infobox was blank.
- Add a `nationality_source` column to `core.player` so we know which source won.

---

### ② Market value

| Source | Access method | Licence | What we get |
|--------|--------------|---------|-------------|
| **Transfermarkt** | ⛔ **Blocked** — ToS §11.1 forbids all automated access | Proprietary | — |
| **Wikidata** (`P2403` — market value) | SPARQL; same open API as above | CC0 | Sparse (only top players), but free |
| **CIES Football Observatory** | Free annual PDF reports + downloadable Excel (manual import) | Research licence | Estimated values for top-500 African players by algorithm |
| **African Football Insider** newsletter | Manual data entry from published reports | Editorial fair use | Curated top-value lists per league |

**Integration plan:**
- Import CIES Excel report annually into `seeds/player_market_value.csv` → seed into `core.player_market_value`.
- Backfill Wikidata `P2403` where available via SPARQL.
- Display in dashboard as "estimated range" with source attribution.

---

### ③ Stats cards — goals, assists, rating per match

| Source | Access method | Licence | What we get |
|--------|--------------|---------|-------------|
| **PSL official** (`psl.co.za/matchcentre`) | HTML spider (allowed; non-commercial clause) | Non-commercial personal/educational | Current season: goals, assists, cards, ratings per player per match |
| **OpenFootball** | Flat-file CSV dump | Public domain | Historical goals per player where recorded |
| **CAF official** (`cafonline.com`) | `robots.txt` returns 404 (unknown policy) — manual download only | Unclear | Match reports for CAF CL & CC |
| **Wikipedia match articles** | Already scraped via `wiki_psl_seasons`; scorers partially captured | CC BY-SA | Goal-scorer names; limited assists |

**Integration plan:**
- Add `wiki_psl_goalscorers` spider to extract scorer names from Wikipedia season articles for leagues where they appear in the results matrix.
- Build `psl_matchcentre` spider (next sprint) to feed `stg_appearance` with per-match stats for RSA_PREM.
- Add `goals_conceded`, `clean_sheets`, `saves` to a `stg_gk_stats` staging table for GK-specific scoring.

---

### ④ Cards (yellow / red) & suspensions

| Source | Access method | Licence | What we get |
|--------|--------------|---------|-------------|
| **PSL official** (`psl.co.za`) | HTML spider (allowed; see above) | Non-commercial | Yellow, red, second-yellow counts per player |
| **Wikipedia** season articles | Partial — some seasons include discipline tables | CC BY-SA | Season card totals; inconsistent |
| **Wikidata `P1352`** (ranking/statistics) | Very sparse for African leagues | CC0 | — |

**Integration plan:**
- Add `card_events` table to `sql/init/` and a `stg_cards` staging model.
- Parse discipline tables from Wikipedia season articles where available.
- Feed `psl_matchcentre` spider into `stg_cards` for current-season data.
- In `talent_score.sql`, deduct points for red cards (e.g., −5 per red card).

---

### ⑤ Injuries & absences

| Source | Access method | Licence | What we get |
|--------|--------------|---------|-------------|
| **Wikipedia player page** (`Injuries` or `Career` section) | Already scraped by `wiki_psl_players` → `fct_player_injuries` | CC BY-SA | Text descriptions; inconsistent structure |
| **Wikidata** | No structured injury property | CC0 | — |
| **TransferRoom** (licensed API) | Commercial API — contact for pricing | Commercial | Availability status per player |
| **PSL official news** (`psl.co.za/news`) | HTML spider (allowed; non-commercial) | Non-commercial | Injury announcements for RSA_PREM |

**Integration plan:**
- Improve the `fct_player_injuries` model to extract structured fields: `injury_type`, `start_date`, `end_date`, `games_missed` from the raw text using a regex / LLM extraction step.
- Add a `player_availability` boolean column to `mart.shortlist` so scouts can filter out injured players.

---

### ⑥ Dashboard improvement road-map

| Priority | Enhancement | Data source | Effort |
|----------|------------|-------------|--------|
| 🔴 High | Player photos on Scout Shortlist card view | Wikipedia infobox `image_url` (already in `core.player`) | Low |
| 🔴 High | GK-specific stats: save %, clean sheets, goals conceded/90 | PSL matchcentre spider | Medium |
| 🟡 Medium | Nationality flags on player cards | Wikidata SPARQL | Low |
| 🟡 Medium | Market value indicator in shortlist table | CIES Excel seed | Low |
| 🟡 Medium | Suspension warning badge | PSL matchcentre / Wikipedia cards table | Medium |
| 🟢 Low | Injury timeline chart per player | `fct_player_injuries` structured extraction | High |
| 🟢 Low | League-strength comparison chart | `mart.league_strength` (already computed) | Low |
| 🟢 Low | Player vs league-average radar chart | `mart.player_percentiles` (already computed) | Medium |

---

### ⑦ Player profile coverage for non-RSA_PREM leagues

Currently `core.player` only contains RSA_PREM players (scraped by `wiki_psl_players`). To populate the Scout Shortlist for other leagues:

1. **Extend `wiki_psl_players` spider** — feed it club Wikipedia URLs from `core.team` for each Wave 1 league. The spider already handles any Wikipedia club page; it just needs a list of URLs.
2. **Build `leagues.yml` → club pages mapping** — for each `team_id` in `seed_team.csv`, add an optional `wikipedia_url` column. The spider then crawls those pages to find squad tables.
3. **Wikidata club query** — for each team, query Wikidata `P17` (country) + `P856` (official website) + squad members (`P54`) to bootstrap the player list without scraping individual player pages.
