# The Data You Don't Collect: Designing Pipelines Around Refusals

A data pipeline can be well tested, well documented, and correctly engineered, and still be built on data it was never allowed to keep. When a provider withdraws access and asks for its data to be deleted, the code does not fail. The pipeline simply loses its foundation, and every model, report, and dashboard built on top of it goes with it. The problem in that situation is not a bug. It is a decision that was made early and never revisited: the decision to collect something without asking whether it should be collected at all.

I have worked as both a software engineer and a data engineer. Most recently, I built a data platform that collects sports statistics from public websites and uses them to analyse player development. Because every source in that project was external, I had to answer a question that most pipeline tutorials skip. The usual question is where to get more data. The more useful question turned out to be what the pipeline should refuse to collect.

This article is about designing data pipelines around deliberate refusals. It applies to any pipeline that depends on data you do not fully control, including scraped websites, third-party APIs, partner file transfers, and even internal systems that hold personal information.

The central idea fits in four words: **collect less, defend everything.**

It matters because a pipeline built on data you do not own lasts only as long as your right to use that data. It also matters because every piece of data you hold is something you must maintain, secure, and, if asked, explain. Refusing data early is far cheaper than removing it later.

This article presents three gates that data should pass through. The first gate controls **which sources** a pipeline may use, based on permission. The second controls **which fields** may enter the warehouse, based on purpose. The third controls **what may leave** the warehouse, based on risk.

If you have ever had to remove a dataset from production because nobody checked whether it could be used, these gates are designed to prevent that situation. We will begin with the first one.

## Gate sources by permission, not accessibility

The first gate decides whether a source enters the pipeline at all. The rule is that a source is allowed only when its terms permit your intended use. The fact that its data can be reached is not enough.

### Robots.txt is not permission

When engineers think about scraping rules, they usually think first of **robots.txt**. This is a file at the root of a website that tells automated clients which paths they should not crawl. A responsible scraper should always obey it. However, robots.txt answers only a technical question about how a crawler should behave. It does not say whether the site's data may be collected, stored, or republished.

I encountered this gap directly while evaluating sources for the sports platform. One website's robots.txt allowed crawling of the pages I needed, but its terms of service prohibited automated collection. A scraper that checked only robots.txt would have behaved politely and still breached the site's terms.

The rule I adopted is straightforward. Robots.txt tells you how to behave on a site, and the terms of service tell you whether you are allowed to collect from it. Both must pass, and the terms of service are the deciding gate.

### Encode the decision where code can enforce it

A rule that exists only in a document or in someone's memory tends to be forgotten when a deadline approaches. For that reason, every source in the platform is recorded in a registry file that stores its legal status next to its technical settings.

```yaml
sources:
  - source_id: wikipedia_season
    licence: Creative Commons Attribution-ShareAlike
    robots_checked: true
    tos_reviewed: true
    allowed: true

  - source_id: psl_official
    licence: Terms not yet reviewed
    robots_checked: false
    tos_reviewed: false
    allowed: false
```

Every scraper reads this file when it starts. If its source is marked `allowed: false`, the scraper refuses to run. There is no override flag and no environment variable that skips the check. Using a new source therefore requires someone to review its terms, record the outcome, and change the value in a commit that is visible in version control.

The enforcement itself is a few lines, and it raises an exception rather than logging a warning, because a warning is something a tired engineer can ignore at midnight.

```python
# ingestion/ingestion/registry.py  (simplified)
class Registry:
    def enforce_allowed(self, source_id: str) -> None:
        """Raise RuntimeError if the source is not marked allowed: true."""
        src = self.get_source(source_id)
        if not src.get("allowed", False):
            raise RuntimeError(
                f"Source '{source_id}' is not allowed to be scraped. "
                "Complete a source audit, then set allowed: true in config/sources.yml."
            )
```

Every spider calls `registry.enforce_allowed(self.source_id)` in its constructor — before any HTTP request is issued — so an unreviewed source cannot be used by accident, even in a quick experiment.


The second entry — `psl_official` in this project — illustrates an important distinction. An official source is often the most accurate source for its own data, but accuracy is not the same as permission. Until its terms have been reviewed, the pipeline does not touch it.

The same pattern works outside scraping. A company that receives files from partners can record each partner's data-sharing agreement in the same way, so that a pipeline cannot process a feed whose agreement has expired.

### Qualifiers and objections

Terms of service differ in how enforceable they are, and that varies between countries. A registry of this kind is not legal advice, and it does not replace it. Its purpose is to ensure that a decision about each source was made, recorded, and enforced, rather than skipped.

A common objection is that publicly visible data is free to use. Visibility, however, is not a licence. A page that anyone can read may still come with conditions on how its content can be collected and reused.

Once the sources are settled, the next decision is what to take from them.

## Gate fields by purpose

The second gate decides which fields enter the warehouse. The rule is that every field must help answer the question the product exists to answer. A field that does not meet that test stays out, even when it is free and easy to collect.

### Start from the question

Every data product should be able to state its central question in one sentence. For the sports platform, that question was which young players are receiving meaningful playing time, performing well, and improving, and how they compare across competitions. For an e-commerce analytics pipeline, the question might be which products and channels drive repeat purchases.

Each field is then judged against that question. In the sports platform, match results, goals, appearances, minutes played, and each player's position and age were essential, because the analysis could not work without them. Secondary fields such as assists and disciplinary records were accepted where available.

### Write down the exclusions

A data contract is an agreement that defines what data a pipeline will provide, including its fields, types, and rules. Most data contracts list only what is included. A stronger contract also lists what is excluded.

The sports platform's contract explicitly excluded betting odds, market valuations, photographs, agent details, salaries, contact information, and social media profiles. Several of these were visible on public websites, and some would have been interesting. None of them helped answer the product's question.

| Category | Decision | Reason |
|---|---|---|
| Results, goals, appearances | Collected | Required to measure playing time and performance |
| Age, position, nationality | Collected | Required to compare players fairly |
| Betting odds, market values | Excluded | Not needed to answer the product's question |
| Photos, contact details, social profiles | Excluded | Personal data with no analytical value |

Writing exclusions down changes how the contract is used. When a contract lists only inclusions, adding a field feels harmless. When it names exclusions, adding a field requires a deliberate discussion about why the earlier decision should change.

The ideal is that this contract is enforced in code, at the boundary between parsing and storage, so that anything a parser produces that the contract does not name is rejected rather than quietly stored. The pattern looks like this:

```python
# aspirational pattern — not yet in the current codebase
from dataclasses import dataclass, fields
from datetime import date

@dataclass(frozen=True)
class MatchRecord:
    source_id: str
    source_url: str
    match_date: date
    home_team_raw: str
    away_team_raw: str
    home_goals: int
    away_goals: int

ALLOWED_FIELDS = {f.name for f in fields(MatchRecord)}

def to_contract(parsed: dict) -> MatchRecord:
    unexpected = set(parsed) - ALLOWED_FIELDS
    if unexpected:
        raise ValueError(f"fields outside the data contract: {sorted(unexpected)}")
    return MatchRecord(**parsed)
```

This check catches the most common way that unwanted data enters a warehouse, which is not a decision to collect it but a parser that happily passes along whatever a page happened to contain. The sports platform currently documents its exclusions rather than enforcing them as a typed boundary — implementing this gate is a concrete next step for tightening the pipeline.


### Qualifiers and objections

A data contract is not permanent. As a product's question evolves, new fields may become necessary. The difference is that each addition becomes an explicit decision, reviewed against the product's purpose, rather than a side effect of whatever a source happens to offer.

The most frequent objection is that storage is cheap, so extra fields cost nothing. Storage is the least expensive part of a field. Each field also requires parsing, testing, documentation, access control, and ongoing maintenance, and each one creates another way for a change in a source to break the pipeline.

Controlling what enters the warehouse solves half of the problem. The third gate controls what leaves it.

## Gate outputs by risk

The third gate decides which data may be published or shared. The rule is that outputs need stricter controls than inputs, because publishing changes who can see the data and how it can be combined with other information.

### Know who the data describes

Data about people deserves particular care, and data about young people deserves even more. In the sports platform, many of the players were between 16 and 21 years old, and some were under 18. Analysing their playing time inside a private warehouse is very different from publishing searchable, ranked profiles of named teenagers.

The same principle applies to customer data, employee data, and patient data. The question is not only whether a value is accurate, but also whether the people it describes would reasonably expect it to be shown in that form.

### Minimise at the export layer

The sports platform applies a small set of fixed rules to anything that leaves the warehouse. Only public sporting information is stored in the first place. Full dates of birth remain internal, where they are needed to calculate ages accurately. Public exports include only the birth year. A documented process allows anyone to request a correction or removal. Before any commercial use, the data protection laws of each relevant country must be reviewed, such as the European Union's General Data Protection Regulation, South Africa's Protection of Personal Information Act, and Kenya's Data Protection Act.

These rules are enforced in the export models rather than in the user interface. That way, no dashboard, file, or API can expose a field that was never meant to leave the warehouse. The ideal pattern replaces a full date of birth with the birth year alone in any public export:

```sql
-- recommended pattern for public exports
select
    player_id,
    display_name,
    extract(year from date_of_birth)::int as birth_year,   -- full date stays internal
    nationality,
    primary_position
from {{ ref('player') }}
```

The sports platform has not yet implemented this boundary: the current public data loader exports `date_of_birth` directly. Applying this pattern to public-facing queries is a pending item on the roadmap. An e-commerce pipeline can follow the same approach by exporting age bands instead of birth dates, or regions instead of full addresses.

### Qualifiers and objections

These rules are a starting point rather than a complete compliance programme. Any team planning to publish or sell data about people should seek legal advice for the countries involved.

A frequent objection is that the underlying facts are already public. That may be true for individual facts. Combining them into ranked and searchable profiles, however, creates something new, and that new product deserves its own review.

## Conclusion

A pipeline that loses its data because of an old sourcing decision fails in a way that no test can catch. The three gates in this article exist to make those decisions deliberately, before they become expensive.

The first gate admits a source only when its terms permit the intended use, and it records that decision where code can enforce it. The second gate admits a field only when it answers the product's question, and it names what is excluded. The third gate controls what leaves the warehouse, with the strictest rules reserved for data about people.

**Collect less, defend everything.**

Every field you collect is a promise to parse it, test it, protect it, and possibly delete it one day. The pipelines that last are the ones that make fewer promises and keep all of them.

Here is a small step you can take this week. Open the list of sources your pipeline depends on, add a column for each source's licence and whether its terms allow your use, and fill it in. Any cell you cannot fill shows you where your next problem is waiting.

*This is the first article in a series on data engineering lessons from building pipelines on external sources. The next article covers entity resolution: how to decide when two records describe the same real-world thing.*

**Tags:** Data Engineering, Data Governance, Data Privacy, Data Contracts, Data Pipelines
