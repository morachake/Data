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
