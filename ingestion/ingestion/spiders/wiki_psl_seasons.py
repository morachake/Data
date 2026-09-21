from datetime import date, datetime, timezone
from urllib.parse import quote

import scrapy

# PSL seasons run August–May. Include the last five completed years plus the current one.
COMPLETED_SEASONS_TO_KEEP = 5


def seasons_through_current() -> list[str]:
    today = date.today()
    current_start = today.year if today.month >= 8 else today.year - 1
    first = current_start - COMPLETED_SEASONS_TO_KEEP
    return [f"{year}–{str(year + 1)[2:]}" for year in range(first, current_start + 1)]


class WikiPslSeasonsSpider(scrapy.Spider):
    name = "wiki_psl_seasons"
    allowed_domains = ["en.wikipedia.org"]

    async def start(self):
        for season in seasons_through_current():
            title = f"{season} South African Premiership".replace(" ", "_")
            url = f"https://en.wikipedia.org/wiki/{quote(title)}"
            yield scrapy.Request(
                url,
                callback=self.parse_season,
                cb_kwargs={"season": season},
                errback=self.missing_season,
            )

    def parse_season(self, response, season):
        scraped_at = datetime.now(timezone.utc).isoformat()
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

            yield {
                "source": "wikipedia",
                "source_url": response.url,
                "season": season,
                "table_index": i,
                "section": section,
                "rows": rows,
                "scraped_at": scraped_at,
            }

    def missing_season(self, failure):
        self.logger.warning("Season page missing: %s", failure.request.url)
