"""
wikipedia_season spider (legacy name: wiki_psl_seasons).

Scrapes Wikipedia season pages for every active league that lists
``wikipedia_season`` as a source.  Emits one RawPageItem per wikitable
found on each page.

Backward compatibility
----------------------
The old item dict format (source, source_url, season, table_index, section,
rows, scraped_at) is preserved in ``payload`` so that loaders/load_raw.py
can continue to work during the Phase 0→1 transition.  Once parsers/ fully
replaces loaders/ (Phase 1), the ``_legacy_dict`` helper can be removed.
"""

from datetime import date, datetime, timezone
from urllib.parse import quote

import scrapy

from ingestion.items import RawPageItem
from ingestion.spiders.base import RegistrySpider

# ---------------------------------------------------------------------------
# Helpers shared with the player spider (kept for backward compat)
# ---------------------------------------------------------------------------
COMPLETED_SEASONS_TO_KEEP = 5


def seasons_through_current() -> list[str]:
    """Return the last N completed PSL seasons plus the current one."""
    today = date.today()
    current_start = today.year if today.month >= 8 else today.year - 1
    first = current_start - COMPLETED_SEASONS_TO_KEEP
    # Use en-dash (–) to match Wikipedia page titles.
    return [f"{year}\u2013{str(year + 1)[2:]}" for year in range(first, current_start + 1)]


def _season_to_wiki(season: str) -> str:
    """Convert config hyphen separator to Wikipedia en-dash (2024-25 → 2024–25)."""
    # If already en-dash, return as-is.
    if "\u2013" in season:
        return season
    parts = season.split("-")
    if len(parts) == 2:
        return f"{parts[0]}\u2013{parts[1]}"
    return season


# ---------------------------------------------------------------------------
# Spider
# ---------------------------------------------------------------------------

class WikiPslSeasonsSpider(RegistrySpider):
    name = "wiki_psl_seasons"
    source_id = "wikipedia_season"
    allowed_domains = ["en.wikipedia.org"]

    async def start(self):
        for league_id, season in self.active_partitions:
            league = self.registry.get_league(league_id)
            title_tpl = league.get(
                "wikipedia_title_template",
                "{season} South African Premiership",
            )
            wiki_season = _season_to_wiki(season)
            title = title_tpl.format(season=wiki_season).replace(" ", "_")
            url = f"https://en.wikipedia.org/wiki/{quote(title)}"
            yield scrapy.Request(
                url,
                callback=self.parse_season,
                cb_kwargs={"league_id": league_id, "season": season},
                errback=self.missing_season,
            )

    def parse_season(self, response, league_id: str, season: str):
        fetched_at = datetime.now(timezone.utc).isoformat()
        for i, table in enumerate(response.css("table.wikitable")):
            rows = []
            for tr in table.css("tr"):
                cells = [
                    " ".join(t.strip() for t in cell.css("::text").getall() if t.strip())
                    for cell in tr.css("th, td")
                ]
                if cells:
                    rows.append(cells)

            section = " ".join(
                table.xpath("preceding::*[self::h2 or self::h3][1]//text()").getall()
            ).strip()

            yield RawPageItem(
                source_id=self.source_id,
                league_id=league_id,
                season=season,
                url=response.url,
                block_type="table",
                block_index=i,
                section=section,
                payload=rows,
                http_status=response.status,
                fetched_at=fetched_at,
            )

    def missing_season(self, failure):
        self.logger.warning("Season page missing: %s", failure.request.url)
