# Choosing an Ingestion Stack: Frameworks, Browsers, and When to Buy Instead

The first decision in any pipeline that collects data from the public web looks trivial. You need to fetch some pages and read some values out of them, and a short Python script with two libraries can do that in an afternoon. The decision stops looking trivial about three weeks later, when the script has grown retry logic, a delay between requests, a way to resume after a crash, a cache so that debugging does not hammer the source, and a growing collection of special cases for pages that load their content in the browser.

I went through this while building a data platform that collects sports statistics from public websites. What began as a single script became an ingestion layer with a defined contract, and choosing the right foundation for it mattered more than any other early technical decision.

This article compares the main options for building an ingestion layer that fetches data from external sources, and it explains how to choose between them. It covers parsing libraries, crawling frameworks, browser automation, and managed scraping services.

The guiding principle fits in five words: **match the tool to the target.**

The choice matters because ingestion is where a pipeline meets the outside world. Everything downstream can be tested, versioned, and controlled. The ingestion layer deals with servers you do not own, formats you did not choose, and changes you will not be told about.

This article covers three decisions. The first is **what kind of tool you actually need**, which depends on how the target site delivers its data. The second is **how to structure the ingestion layer** so it stays maintainable. The third is **when to buy instead of build**, because sometimes the right engineering decision is not to write the collector at all.

If you have ever watched a small scraping script grow into an unmaintainable pile of exceptions, the first decision is where that problem starts.

## Choose the tool that matches the target

The first decision is which category of tool fits your sources. The claim is that most ingestion pain comes from using a tool built for a different kind of target.

### The four categories

**Parsing libraries** such as BeautifulSoup do one job: they take HTML that you have already fetched and let you search it with selectors. They have no networking, no retries, and no scheduling, so they are usually paired with an HTTP client such as `requests` or `httpx`.

A complete job in this category fits in a few lines, which is exactly why it is so tempting.

```python
import httpx
from bs4 import BeautifulSoup

response = httpx.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")
rows = [
    [cell.get_text(strip=True) for cell in tr.select("th, td")]
    for tr in soup.select("table.results tr")
]
```

Everything a framework would provide, including retries, delays between requests, resuming after a crash, and caching during development, is absent here and would have to be written by hand.


**Crawling frameworks** such as Scrapy handle the whole fetch-and-follow cycle. Scrapy is an asynchronous Python framework that provides request queueing, link following, retries, rate limiting, caching, and export pipelines out of the box. It is built for static HTML at scale and does not execute JavaScript on its own, although the `scrapy-playwright` plugin adds that capability when needed.

**Browser automation** such as Playwright runs a real browser engine, so it renders JavaScript exactly as a user's browser would. It can click, scroll, and wait for elements to appear. That power costs memory and time, since every page now runs a browser instead of a single HTTP request.

**Unified libraries** such as Crawlee combine HTTP crawling and browser automation behind one interface, and they add session handling and fingerprint management. Crawlee began in the Node.js ecosystem and now has a Python version as well.

### How to decide in practice

The decision follows the target rather than the language you prefer.

| Target | Sensible choice |
|---|---|
| A handful of static pages, fetched once | An HTTP client plus a parsing library |
| Many static pages, fetched repeatedly | A crawling framework such as Scrapy |
| Pages that build their content in the browser | Browser automation, or a framework with a browser plugin |
| A mix of both, with heavy anti-bot measures | A unified library such as Crawlee |

For the sports platform, the sources were mostly static HTML tables collected on a schedule, across many competitions and seasons. That matched the crawling framework category, so the ingestion layer uses Scrapy. Its built-in throttling, caching, and retry behaviour would otherwise have been rewritten by hand, and its caching in particular made development far less intrusive on the sources.

### Before reaching for a browser

When a page appears to require JavaScript, it is worth opening the browser's developer tools and inspecting the network requests first. Many such pages fetch their data from an endpoint that returns JSON, and requesting that endpoint directly is faster, more stable, and easier to parse than rendering the page. Browser automation is the fallback, not the first response.

In practice the two approaches look like this, and the difference in cost between them is large.

```python
# Preferred: request the JSON endpoint the page itself calls
payload = httpx.get(f"{base_url}/api/v1/results", params={"season": season}).json()
rows = payload["results"]
```

```python
# Fallback for genuinely JavaScript-rendered sources (not currently used in this project):
# install scrapy-playwright and add to custom_settings for that spider only.
# settings.py (or spider custom_settings)
DOWNLOAD_HANDLERS = {
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
```

Rendering turns each page into a browser session, which multiplies memory use and run time. Reserve it for the pages that genuinely require it rather than enabling it across a whole project.


### Qualifiers and objections

Tool categories overlap, and any of them can be made to work with enough effort. The question is how much of that effort you want to spend on infrastructure rather than on your actual data. A reasonable objection is that a framework imposes its own structure and learning curve, which is true. For a single small job, a script is genuinely better. The moment you need scheduled runs across many sources, the framework's structure becomes the cheaper option.

Choosing a tool is only the start. How you structure the code around it decides how long it survives.

## Structure ingestion so it survives change

The second decision is about the shape of the ingestion layer. The claim is that collectors should capture structure, while interpretation belongs in a separate layer.

### Keep collectors thin

In the sports platform, each collector fetches a page, locates the blocks of interest such as tables, and records their structure as rows and cells, along with the page address and the time of collection. A collector never decides what a value means and never performs calculations.

```python
# ingestion/ingestion/spiders/  (pattern — simplified)
def parse(self, response):
    for index, table in enumerate(response.css("table")):
        yield {
            "source_id": self.source_id,
            "league_id": self.league_id,
            "season": self.season,
            "url": response.url,
            "block_type": "table",
            "block_index": index,
            "payload": self.capture_rows(table),   # cell text exactly as captured
            "fetched_at": self.fetched_at,
        }
```

Parsers then read these captured blocks and assign meaning to them. Because the captured output is stored, a parser can be corrected and rerun over data that was collected weeks ago, without touching the source again.

Giving every collector the same constructor arguments is what allows an orchestrator to run one league and season at a time.

```python
# ingestion/ingestion/spiders/base.py  (simplified)
import scrapy
from ingestion.registry import get_registry

class RegistrySpider(scrapy.Spider):
    source_id: str = ""   # subclasses must override

    def __init__(self, league_id: str | None = None, season: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.registry = get_registry()
        # Raises RuntimeError immediately if the source has allowed: false.
        self.registry.enforce_allowed(self.source_id)
        self.league_id = league_id
        self.season = season
```

Every collector in the project inherits from this class, so permission checking and partition arguments are handled once rather than repeated in each spider.


### Be a good client

An ingestion layer is a guest on someone else's infrastructure. The settings below are the ones that matter most, and each has an equivalent in every serious tool.

```python
ROBOTSTXT_OBEY = True
USER_AGENT = "ProjectName/1.0 (+contact-address)"
AUTOTHROTTLE_ENABLED = True
DOWNLOAD_DELAY = 1.0
CONCURRENT_REQUESTS_PER_DOMAIN = 1
HTTPCACHE_ENABLED = True          # during development only
RETRY_TIMES = 3
```

Identifying yourself with a contact address, throttling requests, and caching during development are not only courtesies. They also reduce the chance of being blocked, which is the most common way an ingestion layer fails.

### Qualifiers and objections

Thin collectors mean more files and more indirection, which can feel like overhead on day one. The alternative is a collector that understands your data model, which means every layout change on a website risks corrupting data that has already been interpreted.

Sometimes, however, the best ingestion code is the code you never write.

## Know when to buy instead of build

The third decision is whether to build the collector at all. The claim is that ingestion should be built only when the data cannot be obtained another way at an acceptable cost.

### The alternatives to writing a collector

The first alternative is an official API or a bulk download. These are almost always more stable, better documented, and less legally risky than collecting pages, and they should be checked before any code is written.

The second alternative is a commercial data provider. A paid feed converts an engineering problem into a subscription, which is often the correct trade when the data is central to the business.

The third alternative is a managed scraping service that handles proxies, browser rendering, and anti-bot measures. These are worth considering when the difficulty lies in access rather than in parsing.

### How to compare the options honestly

The comparison should include the full cost of building, not just the initial development time.

| Option | Strengths | Weaknesses |
|---|---|---|
| Build your own collectors | Full control, no per-record cost, works where no product exists | Ongoing maintenance, blocked requests, legal review needed |
| Official API or bulk export | Stable schema, clear terms, low maintenance | May not exist, may be incomplete, may cost money |
| Commercial data provider | Reliable and supported | Recurring cost, dependence on one vendor, licence limits reuse |
| Managed scraping service | Handles access problems well | Per-request cost, still requires your own parsing, same legal questions |

In the sports platform, no affordable official source covered the competitions I needed, which is exactly the situation where building is justified. The architecture still treats a future paid source as a first-class option, so buying later remains an easy decision rather than a rewrite.

### Qualifiers and objections

Cost comparisons change with scale. A paid API that looks expensive for one dataset can be far cheaper than the engineering time required to collect and maintain ten. It is worth repeating this comparison once a year rather than treating the original decision as permanent.

The legal position also differs between options. A commercial provider gives you a licence that defines what you may do with the data, while collecting pages yourself leaves that question to you.

## Conclusion

The script that grows out of control is not a failure of discipline. It is what happens when a tool designed for one kind of target is used for another, and when interpretation is mixed into collection.

Choosing an ingestion stack comes down to three decisions. Match the tool to the target, using parsing libraries for one-off jobs, crawling frameworks for repeated static collection, and browser automation only when rendering is genuinely required. Structure the layer so that collectors capture structure and parsers assign meaning. Finally, check whether an API, a provider, or a managed service would be cheaper than the pipeline you are about to maintain.

**Match the tool to the target.**

Ingestion is the only part of your pipeline that depends on strangers. Everything you do to keep it simple, polite, and replaceable pays for itself the first time a source changes.

This week, take one collector you maintain and check two things: whether it identifies itself with a contact address, and whether it would still be the right tool if the target site moved its data behind JavaScript tomorrow.

*This is the seventh article in a series on data engineering lessons from building pipelines on external sources. The next article compares orchestration tools and explains why the choice matters more than the schedule it produces.*

**Tags:** Data Engineering, Web Scraping, Python, Scrapy, Data Ingestion
