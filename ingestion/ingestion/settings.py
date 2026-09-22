BOT_NAME = "ingestion"
SPIDER_MODULES = ["ingestion.spiders"]
NEWSPIDER_MODULE = "ingestion.spiders"

# Identify the project and provide a contact address.
USER_AGENT = (
    "AfricanFootballData/1.0 "
    "(+https://github.com/african-football-data; africanfootballdata@example.com)"
)

ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 1.0          # overridden per-source by RegistrySpider
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
CONCURRENT_REQUESTS_PER_DOMAIN = 1   # polite; one request at a time per host

HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400    # disabled in scheduled runs via -s HTTPCACHE_ENABLED=False

RETRY_TIMES = 3

# RegistrySpider-based spiders write via RawWriterPipeline (no FEEDS needed).
# wiki_psl_players keeps its own custom_settings FEEDS for backward compat.
ITEM_PIPELINES = {
    "ingestion.pipelines.ValidateItemPipeline": 100,
    "ingestion.pipelines.RawWriterPipeline": 200,
    "ingestion.pipelines.RunStatsPipeline": 300,
}

FEED_EXPORT_ENCODING = "utf-8"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
