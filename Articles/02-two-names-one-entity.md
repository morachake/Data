# Two Names, One Entity: Entity Resolution You Can Trust

A customer signs up with a personal email address and later buys something using a work address. A supplier appears as "Acme Ltd" in the finance system and "ACME Limited" in the procurement system. A patient's surname is spelled one way at a clinic and another way at a pharmacy. Each system is internally consistent. When their data is combined, however, one person becomes two records, or two different people are blended into one.

I have met this problem in every integration project I have worked on. It was especially visible in a sports data platform I built recently, which combines statistics from several public sources. In that project, a single competition appeared under its official name, its governing body's name, and its sponsor's name, depending on the source. Individual players appeared with different spellings, different name orders, and sometimes only a surname.

This article is about **entity resolution**, the process of deciding which records, across one or more sources, describe the same real-world thing and linking them to a single identifier. It is sometimes called record linkage or deduplication, and it sits underneath customer analytics, fraud detection, master data management, and any report that combines data from more than one system.

The main lesson fits in five words: **a wrong merge is corruption.**

Entity resolution matters because every downstream number depends on it. If one customer is split across two records, each record understates their value. If two customers are merged into one, the resulting profile describes someone who does not exist, and every metric built on that profile is wrong.

This article covers three stages. The first stage makes records **comparable** before any comparison happens. The second stage makes decisions **asymmetrically**, because the two kinds of error have very different costs. The third stage makes decisions **durable**, so that human judgment is not lost the next time the pipeline runs.

If you have ever found a customer counted twice in a report, or two customers blended into one, you already know how quietly these errors spread. We will start with preparation.

## Make records comparable before comparing them

The first stage prepares records so that similarity scores mean something. The claim is that many matching errors are caused before any comparison takes place, either by inconsistent cleaning or by comparing records that never needed to be compared.

### Normalise in one place

**Normalisation** means converting values into a standard form before comparing them. For names, this usually involves converting text to lowercase, removing accents and punctuation, removing stray characters such as footnote markers, and unifying known spelling variants. For addresses, it may involve standardising abbreviations such as "St" and "Street". For company names, it may involve removing legal suffixes such as "Ltd" and "Limited".

In the sports platform, names arrived with different transliterations, different word orders, and occasional footnote markers inside the name field. The normalisation step handled all of these and then sorted the words in each name, so that "Omondi Brian" and "Brian Omondi" produced the same normalised value.

The most important design decision was to keep all normalisation in a single shared module. If each source's parser cleaned values in its own way, the same entity would be normalised slightly differently depending on where it came from, and matching would fail for reasons that are very hard to see.

The module itself is small, and keeping it small is part of the point, because every rule in it applies to every source equally.

```python
# entity_resolution/name_normalise.py  (simplified)
from parsers.common.names import normalise   # language-aware: lowercases, strips
                                              # accents, footnote markers, punctuation

def canonical(name: str) -> str:
    """Sorted-token canonical form — word order becomes irrelevant."""
    return normalise(name)   # normalise() returns tokens sorted alphabetically

def blocking_key(name: str) -> str:
    """4-char prefix of the canonical form; candidates sharing a key are scored."""
    canon = canonical(name)
    return canon[:4] if len(canon) >= 4 else canon
```

The shared normalisation module (`parsers/common/names.py`) handles lowercasing, accent removal, and known transliteration variants so that a source writing the family name first produces the same canonical value as one that writes it last.


### Compare only plausible candidates

Comparing every record with every other record becomes expensive very quickly. It also increases the number of false matches, because every additional comparison is another chance for two different entities to look alike.

**Blocking** limits comparisons to candidate pairs that share a meaningful attribute. A customer pipeline might compare records only when they share a postcode or a phone number. In the sports platform, two player records were compared only when they shared at least one blocking key: the same team in the same season, the same date of birth, or the same normalised surname.

A blocking key does not decide whether two records match. It decides which pairs are worth scoring.

In code, a blocking key is simply a label that two records must share before they are compared at all.

```python
# entity_resolution/player_matcher.py  (simplified)
from entity_resolution.name_normalise import blocking_key

# All candidates sharing the same 4-char key are scored against each other.
# Candidates from the same source are skipped (deduplication is not the goal).
for i in range(len(group)):
    for j in range(i + 1, len(group)):
        a, b = group[i], group[j]
        if a.source_id == b.source_id:
            continue
        score = _fuzzy_score(a.player_raw, b.player_raw)
        score += _dob_score(a.dob_raw, b.dob_raw)
```

Grouping by the first four characters of the canonical name turns a comparison of every record against every other record into a small set of plausible candidates per run.


### Qualifiers and objections

Blocking can miss true matches. If a customer moves house and changes phone number, two of their records may never be compared. In a well-designed system, those records begin as separate entities and can be linked later when stronger evidence appears. As the next section explains, that outcome is usually the safer mistake.

A reasonable objection is that modern fuzzy matching libraries are fast enough to compare every pair. Speed, however, is only part of the problem. Comparing everything still produces more false candidates, and false candidates are exactly what the decision stage must guard against.

Once records are comparable, the next question is what to do with a similarity score.

## Decide asymmetrically

The second stage turns similarity scores into decisions. The claim is that entity resolution produces two kinds of error with very different consequences, and a trustworthy system should treat them differently.

### Score with evidence, not only names

Each candidate pair receives a similarity score. The sports platform uses RapidFuzz, an open-source Python library for fuzzy string matching, to compare names using token-based similarity. The name score is then adjusted using supporting evidence. Matching dates of birth increase the score. Conflicting dates of birth reduce it sharply. Belonging to the same team in the same season adds further confidence.

In many domains, a single strong attribute is more informative than a name. Two customers with similar names and different dates of birth are probably different people. Two customers with similar names and the same date of birth and postcode are very likely the same person.

### Two errors, two costs

A **missed match** leaves one entity split across two records. Its activity is divided, so each record looks smaller than the truth. This error is a gap. It is visible to anyone who looks for duplicates, and it can be corrected later.

A **wrong merge** combines two different entities into one record. Their histories are blended into a profile that describes neither of them. Nothing appears broken, but every metric built on that profile is wrong. This error is corruption.

Because the costs are different, the sports platform does not rely on a single threshold. Instead, it uses three outcomes.

| Score | Outcome |
|---|---|
| 92 or above, with no conflicting date of birth | Linked automatically to the existing entity |
| 75 to 91 | Sent to a queue for human review |
| Below 75 | Created as a new entity |

The middle range is intentionally wide. Reviewing a borderline pair costs a person one decision. An incorrect automatic merge can contaminate every report that includes the affected entity.

Both the scoring and the decision live in one place, so the thresholds can be reviewed and changed as a unit.

```python
# entity_resolution/player_matcher.py
from rapidfuzz import fuzz
from entity_resolution.name_normalise import canonical

THRESHOLD_HIGH = 92   # auto-accept
THRESHOLD_LOW  = 75   # auto-reject (grey zone → review queue)

def _fuzzy_score(a: str, b: str) -> float:
    return fuzz.WRatio(canonical(a), canonical(b))

def _dob_score(dob_a, dob_b) -> float:
    if not dob_a or not dob_b:
        return 0.0                     # missing DOB contributes nothing
    if dob_a[:10] == dob_b[:10]:
        return +15.0                   # exact date match
    if dob_a[:4] == dob_b[:4]:
        return +10.0                   # same year only
    return -5.0                        # conflicting year — mild penalty

def decide(value: float) -> str:
    if value >= THRESHOLD_HIGH:
        return "auto_accept"
    if value < THRESHOLD_LOW:
        return "auto_reject"
    return "review_queue"
```

A conflicting date of birth lowers the score only slightly in this model. The main guard against a wrong merge is the wide review range: any pair that scores below 92 and above 75 goes to a human rather than being merged automatically.


### Qualifiers and objections

These thresholds are specific to the data they were designed for, which contained names that varied across languages and sources. Another dataset would need its own thresholds, set by reviewing a sample of real candidate pairs.

The obvious objection is that a wide review range creates manual work. It does create work. The alternative is allowing the system to make the most expensive kind of mistake without anyone noticing. When human attention is limited, it should be spent where errors cost the most.

A review queue is only useful if reviewers' decisions persist, which leads to the third stage.

## Make decisions durable

The third stage stores decisions so that they survive future pipeline runs. The claim is that an entity resolution system is only as trustworthy as its memory.

### Record how every link was made

Every link between a source value and an internal identifier should be stored together with the method used, the score, and the time of the decision. The sports platform uses an alias table for this purpose.

```sql
-- sql/init/004_entity_resolution.sql
CREATE TABLE IF NOT EXISTS core.player_alias (
    alias           TEXT        NOT NULL,
    source_id       TEXT        NOT NULL,
    player_id       TEXT        NOT NULL REFERENCES core.player(player_id),
    method          TEXT        NOT NULL DEFAULT 'auto_accept'
        CHECK (method IN ('auto_accept', 'manual_review', 'seeded')),
    score           NUMERIC(5,2),
    resolved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (alias, source_id)
);
```

Every link can be explained: when someone asks why two records were merged, the answer is a row in this table. One rule worth encoding — not yet fully implemented in this codebase — is that automated runs should never overwrite a `manual_review` decision. At present the `ON CONFLICT DO UPDATE` path replaces any existing row unconditionally; protecting manual decisions from later overwriting would require a check on `method` before the update fires.

### Give names a time window

Names also change over time within a single source. A company is renamed after an acquisition but remains the same legal entity. A retired product name is later reused for a different product. A lookup table that maps a name directly to an identifier cannot handle both situations.

The solution is to give each alias a validity period. The simplified example below shows one organisation that was renamed in 2021 and a different organisation that later adopted its old name.

```csv
alias,source,entity_id,valid_from,valid_to
Coastal Stars,source_a,ORG_014,2015-08-01,2021-06-30
Coastal United,source_a,ORG_014,2021-07-01,
Coastal Stars,source_a,ORG_031,2024-08-01,
```

With validity dates in place, a name resolves to an identifier only within its time window. Readers familiar with slowly changing dimensions will recognise the pattern, applied here to identifiers instead of descriptive attributes.

Resolving a name then becomes a join with a date condition, which is easy to read and easy to test.

```sql
-- transform/models/core/match.sql  (simplified)
select
    m.league_id,
    m.season,
    ha.team_id as home_team_id,
    aa.team_id as away_team_id
from {{ ref('stg_match') }} m
join {{ ref('team_alias') }} ha
  on ha.alias     = m.home_team_raw
 and ha.source_id = m.source_id
join {{ ref('team_alias') }} aa
  on aa.alias     = m.away_team_raw
 and aa.source_id = m.source_id
```

Team aliases carry `valid_from` and `valid_to` columns for handling renames, but the current join does not yet filter on date. When a name appears that has no alias row at all, the join produces no row, and a not-null test on the resulting identifier turns that silence into a failed build.


### Store confidence as data

Some attributes are important enough to carry a confidence level of their own. In the sports platform, age affects almost every metric, so each player has a date-of-birth confidence value. The value is high when two independent sources agree, medium when one source provides a full date, low when sources disagree or only the year is known, and unknown when no date is available. Players with an unknown date of birth receive a neutral default in the talent score rather than being excluded, and they appear in rankings with their confidence level visible alongside the result. A stricter version — excluding unknowns from age-sensitive tiers — remains a design option worth revisiting as source coverage improves.

The same approach works for any attribute that drives important decisions, such as a customer's country for tax purposes or a supplier's registration number.

### Qualifiers and objections

A common objection is that rebuilding every link from scratch on each run is simpler and keeps the pipeline idempotent, meaning that running it twice produces the same result. Idempotency does not require forgetting. Manual decisions can be treated as an input to each run, exactly like source data, and the result remains reproducible.

## Conclusion

A competition with three names is a minor inconvenience. A customer, patient, or player with three names, or three people sharing one record, is a problem that silently shapes every result a data product produces.

Trustworthy entity resolution begins by making records comparable, with normalisation in one place and blocking to limit which pairs are compared. It continues by deciding asymmetrically, sending uncertain matches to people instead of guessing. It ends by making decisions durable, with recorded methods, dated aliases, and confidence stored as data.

**A wrong merge is corruption.**

The records you merge today become the facts your users rely on tomorrow. Treat every merge as a claim you may one day have to defend.

Before you move on, find one join in your own pipeline that matches records by name or email address. Write down what would happen if it merged two different people. If the answer worries you, that join is where your review queue should begin.

*This is the second article in a series on data engineering lessons from building pipelines on external sources. The next article covers source failure, including what to do when a source keeps responding but stops returning data.*

**Tags:** Data Engineering, Entity Resolution, Data Quality, Master Data Management, Python
