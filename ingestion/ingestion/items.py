"""
Scrapy item definitions.

Every spider emits RawPageItem — one item per extracted block (table, match
report, squad list, text section).  No business logic lives here; parsing
happens in parsers/.

Field descriptions
------------------
run_id        UUID assigned by RawWriterPipeline at spider open — groups
              all items from a single scrape run.
source_id     From sources.yml; must match an `allowed: true` entry.
league_id     From leagues.yml partition key.
season        Season label as stored in leagues.yml (e.g. "2024-25").
url           Full URL of the fetched page.
block_type    One of: table | match_report | squad | text
block_index   Zero-based position of this block on the page.
section       Nearest preceding heading on the page (for context).
payload       Extracted structure: list of row-lists for tables, or a dict
              for match reports/squad blocks.
http_status   HTTP status code of the response.
fetched_at    ISO-8601 UTC timestamp of the fetch.
content_hash  MD5 of payload (JSON-serialised, sorted keys).  Lets parsers
              skip unchanged pages on subsequent runs.
"""

import scrapy


class RawPageItem(scrapy.Item):
    run_id = scrapy.Field()
    source_id = scrapy.Field()
    league_id = scrapy.Field()
    season = scrapy.Field()
    url = scrapy.Field()
    block_type = scrapy.Field()
    block_index = scrapy.Field()
    section = scrapy.Field()
    payload = scrapy.Field()
    http_status = scrapy.Field()
    fetched_at = scrapy.Field()
    content_hash = scrapy.Field()
