"""
rsssf_tables spider.

Scrapes RSSSF (Rec.Sport.Soccer Statistics Foundation) season pages.
RSSSF pages are mostly plain-text HTML: match results are listed one per line
in the format:

    Team A - Team B  2:1  (or 2-1, 2–1)

Season pages are found via a predictable URL structure.  The spider discovers
the correct page URL from a per-league ``rsssf_url_template`` in leagues.yml
if present; otherwise it builds a best-effort URL from the known RSSSF
country-code structure.

Each scraped page is emitted as a single RawPageItem with ``block_type=text``
containing the full page text.  All result parsing happens in parsers/rsssf_tables.py.
"""

from datetime import datetime, timezone
from urllib.parse import urljoin

import scrapy

from ingestion.items import RawPageItem
from ingestion.spiders.base import RegistrySpider

# RSSSF URL patterns per country code (best-effort; override with
# rsssf_url_template in leagues.yml for leagues that don't fit the pattern).
_COUNTRY_PATH: dict[str, str] = {
    "RSA_PREM":    "tablesS/safr.html",
    "EGY_PL":      "tablesE/egyp.html",
    "MAR_BOTOLA":  "tablesM/moroc.html",
    "KEN_PL":      "tablesK/keny.html",
    "TZA_PL":      "tablesT/tanz.html",
    "ALG_L1":      "tablesA/alge.html",
    "TUN_L1":      "tablesT/tuni.html",
    "NGA_NPFL":    "tablesN/nige.html",
    "CIV_L1":      "tablesC/ivco.html",
    "GHA_GPL":     "tablesG/ghan.html",
}

BASE = "https://rsssf.org/"


class RssSfTablesSpider(RegistrySpider):
    name = "rsssf_tables"
    source_id = "rsssf_tables"
    allowed_domains = ["rsssf.org"]

    async def start(self):
        seen_urls: set[str] = set()
        for league_id, _season in self.active_partitions:
            league = self.registry.get_league(league_id)
            # Use per-league override URL if provided.
            tpl = league.get("rsssf_url_template")
            if tpl:
                url = tpl
            elif league_id in _COUNTRY_PATH:
                url = urljoin(BASE, _COUNTRY_PATH[league_id])
            else:
                self.logger.warning(
                    "No RSSSF URL known for %s — add rsssf_url_template to leagues.yml",
                    league_id,
                )
                continue

            # Each league has one page covering all seasons; only fetch once.
            if url in seen_urls:
                continue
            seen_urls.add(url)

            yield scrapy.Request(
                url,
                callback=self.parse_page,
                cb_kwargs={"league_id": league_id},
                errback=self.missing_page,
            )

    def parse_page(self, response, league_id: str):
        fetched_at = datetime.now(timezone.utc).isoformat()
        # Emit the whole page as one text block; the parser does the season
        # splitting and result extraction.
        text = "\n".join(response.css("body *::text").getall())
        yield RawPageItem(
            source_id=self.source_id,
            league_id=league_id,
            # RSSSF pages cover multiple seasons — use "all" as a sentinel;
            # the parser splits by season marker.
            season="all",
            url=response.url,
            block_type="text",
            block_index=0,
            section="",
            payload={"text": text},
            http_status=response.status,
            fetched_at=fetched_at,
        )

    def missing_page(self, failure):
        self.logger.warning("RSSSF page missing or unreachable: %s", failure.request.url)
