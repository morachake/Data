"""
psl_official spider.

⚠️  GATED: this spider will raise RuntimeError at startup unless
    sources.yml has `allowed: true` for `psl_official`.

    Per notes.md: the PSL site allows non-commercial / educational use
    only. Flip the flag after confirming that your use case qualifies and
    after running an explicit audit (docs/source_audit/RSA_PREM.csv).

Targets
-------
  /matchcentre             — fixture list for current season
  /matchcentre/detail/<id> — individual match report: lineups, scorers,
                             substitution minutes

Emits
-----
  One RawPageItem per match detail page with:
    block_type = "match_report"
    payload    = { "lineups": {...}, "goals": [...], "substitutions": [...] }
"""

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import scrapy

from ingestion.items import RawPageItem
from ingestion.spiders.base import RegistrySpider

BASE_URL = "https://www.psl.co.za"
MATCHCENTRE = "/matchcentre"


class PslOfficialSpider(RegistrySpider):
    name = "psl_official"
    source_id = "psl_official"
    allowed_domains = ["psl.co.za", "www.psl.co.za"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # source_id = 'psl_official' with allowed: false will cause
        # RegistrySpider.__init__ to call enforce_allowed() → RuntimeError.
        # We never reach this point until the flag is flipped.

    async def start(self):
        league = self.registry.get_league("RSA_PREM")
        seasons = league.get("seasons", [])
        if self.season:
            seasons = [s for s in seasons if s == self.season]

        for season in seasons:
            yield scrapy.Request(
                urljoin(BASE_URL, MATCHCENTRE),
                callback=self.parse_matchcentre,
                cb_kwargs={"season": season},
                errback=self.on_error,
            )

    def parse_matchcentre(self, response, season: str):
        """
        Parse the matchcentre listing page for fixture links.
        The PSL site renders via JS; if this returns empty, inspect
        Network tab for a JSON endpoint and switch to that instead.
        """
        # Look for match detail links:  /matchcentre/detail/<id>
        detail_hrefs = response.css(
            "a[href*='/matchcentre/detail/']::attr(href)"
        ).getall()

        if not detail_hrefs:
            self.logger.warning(
                "No match detail links found on %s — page may be JS-rendered. "
                "Check Network tab for JSON endpoints and update the spider.",
                response.url,
            )
            return

        for href in detail_hrefs:
            url = urljoin(BASE_URL, href)
            yield scrapy.Request(
                url,
                callback=self.parse_match_detail,
                cb_kwargs={"season": season},
                errback=self.on_error,
            )

    def parse_match_detail(self, response, season: str):
        """
        Parse a single match report page.
        Extracts lineups, goals (with minutes), and substitutions.
        """
        fetched_at = datetime.now(timezone.utc).isoformat()

        # ── Lineups ──────────────────────────────────────────────────────
        lineups: dict[str, list[dict]] = {}
        for team_block in response.css(".lineup-team, .team-lineup"):
            team_name = " ".join(
                team_block.css(".team-name::text, h3::text").getall()
            ).strip()
            if not team_name:
                continue
            players: list[dict] = []
            for row in team_block.css(".player-row, li.player"):
                number = " ".join(row.css(".shirt-number::text").getall()).strip()
                name = " ".join(row.css(".player-name::text").getall()).strip()
                is_sub = bool(row.css(".substitute, .sub"))
                if name:
                    players.append({
                        "shirt_number": int(number) if number.isdigit() else None,
                        "name": name,
                        "started": not is_sub,
                    })
            lineups[team_name] = players

        # ── Goals ────────────────────────────────────────────────────────
        goals: list[dict] = []
        for evt in response.css(".goal-event, .event-goal"):
            player = " ".join(evt.css(".scorer::text, .player::text").getall()).strip()
            team = " ".join(evt.css(".team::text").getall()).strip()
            minute_text = " ".join(evt.css(".minute::text").getall()).strip()
            minute_m = re.search(r"(\d+)", minute_text)
            is_own = bool(evt.css(".own-goal"))
            is_pen = bool(evt.css(".penalty"))
            goals.append({
                "scorer": player,
                "team": team,
                "minute": int(minute_m.group(1)) if minute_m else None,
                "is_own_goal": is_own,
                "is_penalty": is_pen,
            })

        # ── Substitutions ────────────────────────────────────────────────
        substitutions: list[dict] = []
        for sub in response.css(".substitution-event, .event-sub"):
            off = " ".join(sub.css(".player-off::text").getall()).strip()
            on = " ".join(sub.css(".player-on::text").getall()).strip()
            minute_text = " ".join(sub.css(".minute::text").getall()).strip()
            minute_m = re.search(r"(\d+)", minute_text)
            substitutions.append({
                "player_off": off,
                "player_on": on,
                "minute": int(minute_m.group(1)) if minute_m else None,
            })

        yield RawPageItem(
            source_id=self.source_id,
            league_id="RSA_PREM",
            season=season,
            url=response.url,
            block_type="match_report",
            block_index=0,
            section="",
            payload={
                "lineups": lineups,
                "goals": goals,
                "substitutions": substitutions,
            },
            http_status=response.status,
            fetched_at=fetched_at,
        )

    def on_error(self, failure):
        self.logger.error("PSL spider error: %s", failure)
