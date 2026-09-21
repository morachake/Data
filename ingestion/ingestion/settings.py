BOT_NAME = "ingestion"
SPIDER_MODULES = ["ingestion.spiders"]
NEWSPIDER_MODULE = "ingestion.spiders"

# Identify yourself with a way to contact you
USER_AGENT = "AfricanFootballData/0.1 (+https://github.com/african-football-data)"

ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 1.0
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
CONCURRENT_REQUESTS_PER_DOMAIN = 2

# Cache pages during development so you don't re-hit sites while debugging
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400

# Every run lands as a new timestamped JSONL file in the raw layer
FEEDS = {
    "../data/raw/%(name)s/%(time)s.jsonl": {"format": "jsonlines", "encoding": "utf8"},
}

FEED_EXPORT_ENCODING = "utf-8"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
