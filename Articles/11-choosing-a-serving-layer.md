# Choosing a Serving Layer: Dashboards, Applications, and Static Sites

A data platform is judged by its last mile. Nobody outside the team sees the collectors, the models, or the tests. They see a page, and they decide there whether the work is useful. That page is usually built with whichever dashboard tool the engineer already knows, which is how a great many data products end up as prototypes that were never replaced.

I made that decision twice while building a data platform that analyses statistics collected from public sources. The first serving layer was an internal dashboard for exploring models and checking data quality. The second was a public site intended for people who would never know what a pipeline is. Trying to make one tool do both jobs was the mistake that taught me the most.

This article compares the main options for serving analytical data and explains how to choose between them. It covers script-based dashboard frameworks, application frameworks, static site generators, and business intelligence tools.

The rule behind the choice fits in five words: **pick the tool per audience.**

This matters because serving is where the value of everything upstream is either realised or lost. A correct number that nobody can find, or that loads too slowly to use, has the same practical value as a wrong one.

This article covers three decisions. The first is **identifying your audience and its requirements**, which determines everything else. The second is **choosing between the four categories of tool**. The third is **knowing when to move on from a prototype**, because the signals are consistent and easy to recognise.

If your only serving layer today is the first tool you happened to learn, the first decision is where to start.

## Identify the audience before the tool

The first decision is about requirements rather than technology. The claim is that the right serving tool follows directly from who will use the output and under what conditions.

### The questions that decide the answer

Who uses this, and how often? A weekly internal review has different needs from a public page shared on social media.

Do users need to explore or to read? Exploration needs filters, inputs, and state. Reading needs speed, clarity, and links that can be shared.

How many people will use it at once, and on what devices? A tool used by three colleagues on laptops can afford to be slow. A public page opened on phones over mobile networks cannot.

Does it need authentication, and does it write data back? Any product that captures input, such as reviews or approvals, is an application, and it should be built as one.

Finally, how often does the data change? Data that updates weekly can be precomputed and published as static files, which removes an entire category of operational work.

### The two audiences in the sports platform

The internal audience is me and anyone helping with the data. The requirements are fast iteration, deep filters, and direct access to the database. Aesthetics do not matter.

The public audience is people interested in the sport. The requirements are quick loading on phones, pages with addresses that can be shared, low hosting cost, and the ability to survive a burst of traffic if a page is widely shared. Deep interactivity matters far less.

Those are different products, and they deserve different tools.

### Qualifiers and objections

The obvious objection is that maintaining two serving layers costs more than maintaining one. It does, in code. It usually costs less in aggravation, because each tool is used for what it is good at. The shared work sits in the models underneath, which both layers read.

With the audiences clear, the categories of tool become easier to compare.

## Choose the category, then the tool

The second decision is which kind of tool to use. The claim is that the four categories differ in their execution model, and that this model matters more than their feature lists.

### Script-based dashboard frameworks

Tools such as Streamlit and Panel run a Python script from top to bottom whenever an input changes. That model makes the first version remarkably quick to build, which is why they dominate internal prototypes. The same model becomes a limitation as an application grows, since complex state and fine-grained layout control work against the rerun cycle.

A useful internal view takes very little code, and the caching decorator is doing important work, because without it the database would be queried on every interaction.

```python
# serving/app.py  (simplified)
import pandas as pd
import streamlit as st
from serving.db import shortlist   # queries mart.shortlist in Postgres

@st.cache_data(ttl=300)            # 5-minute cache; database, not a Parquet file
def load_players(**filters) -> pd.DataFrame:
    return shortlist(**filters)

players = load_players()
positions = st.multiselect("Position", sorted(players.position.unique()))
age_min, age_max = st.slider("Age range", 16, 35, (17, 24))

view = players if not positions else players[players.position.isin(positions)]
view = view[view.age.between(age_min, age_max)]
st.dataframe(view.sort_values("talent_score", ascending=False), hide_index=True)
```

Every widget interaction runs this script again from the first line. That is acceptable for a page like this one, and it becomes painful as soon as the product needs forms, multi-step flows, or state that must survive an interaction.


They are the right choice for internal exploration, quick demonstrations, and anything you expect to change weekly.

### Application frameworks

Tools such as Reflex, NiceGUI, and Dash use an event-driven model, where an action updates part of the page rather than rerunning everything. Reflex compiles a Python application into a React front end, NiceGUI builds on FastAPI with a component library, and Dash uses a callback model with strong charting support.

They are the right choice for products with real users, forms, authentication, or fine-grained interaction, and for anything that captures input rather than only displaying it.

### Static site generators for data

Tools such as Evidence and Observable Framework take a different approach. They run your queries or scripts at build time, produce ordinary web pages, and publish them as files. Evidence lets you write reports in SQL and Markdown, while Observable Framework pairs a JavaScript front end with data loaders that can be written in any language, including Python.

Because the output is plain files, hosting is cheap or free, pages load quickly, and traffic spikes are absorbed by the host rather than by your database. That suits public data products whose data refreshes on a schedule. Note that Observable's own hosting service for these applications was deprecated in 2025, so the current approach is to deploy the generated site to a static host of your choice.

In this model, a data loader is simply a script that runs during the build and writes its output to standard output, which the generator then captures as a file.

```python
# observable/src/data/shortlist.csv.py — executed at build time, never at page load
import sys
from _pg import query, emit_csv   # connects to Postgres using env vars

rows = query("""
    select player_id, full_name, position, season, league_id,
           age_at_midpoint as age, data_tier as tier, talent_score,
           appearances, minutes_played, goals, goals_per90
    from mart.shortlist
    order by talent_score desc nulls last
""")
emit_csv(rows, sys.stdout)
```

Because the query runs once per build rather than once per visitor, Postgres is never exposed to public traffic, and the cost of a page that is widely shared is the same as the cost of a page nobody opens.


### Business intelligence tools

Tools such as Metabase and Superset connect to a database and let users build their own charts and dashboards without writing code. They are the right choice for internal reporting across a team, and the wrong choice for building a specific, designed product experience.

### How the sports platform uses them

The internal layer is a script-based dashboard, because it changes constantly and only a few people use it. The public layer is a static site generated from exported data and rebuilt when the pipeline runs, because it must be fast, shareable, and cheap to host. If the platform later needs accounts, saved lists, or user input, that part will become an application rather than an extension of either layer.

### Qualifiers and objections

These categories are not rigid, and each tool can be pushed beyond its natural range. A script-based dashboard can be deployed publicly, and a static site can include a surprising amount of interactivity through client-side code. The question is how much effort you want to spend fighting a tool's execution model.

Knowing when you have reached that point is the last decision.

## Recognise when to move on

The third decision is about timing. The claim is that the signals for outgrowing a serving tool are consistent, and that acting on them early is cheaper than a rebuild under pressure.

### The signals

The first signal is state. When you are working around the tool's execution model to keep values in place, the model no longer fits the product.

The second signal is performance under real conditions. A page that takes several seconds to load on a laptop will be worse on a phone, and public users will simply leave.

The third signal is cost and reliability. When a public dashboard needs a server that must stay running, and a traffic spike affects your database, a precomputed static site removes both problems.

The fourth signal is the audience itself. As soon as people outside your team depend on a page, requirements such as shareable links, reasonable design, and predictable availability stop being optional.

### Reduce the cost of switching

Two habits make a change of serving tool cheap. First, keep all logic in the data layer, so the serving code only reads tables or files and renders them. Second, define a stable output contract, such as a set of published tables or files, so a new front end can be built against the same contract without touching the pipeline.

In the sports platform, both layers read from the same `mart.shortlist` table in Postgres, which means replacing either front end is a serving project rather than a platform project. Streamlit queries the table at runtime; Observable queries it at build time and bakes the result into static files.

An explicit output contract — a checked list of columns that may leave the mart — is worth maintaining. The pattern looks like this:

```python
# aspirational pattern — not yet in the codebase
PUBLIC_COLUMNS = ["player_id", "full_name", "position", "season", "talent_score", "data_tier"]

def publish(frame):
    missing = set(PUBLIC_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"published contract is missing columns: {sorted(missing)}")
    return frame[PUBLIC_COLUMNS]
```

This function does two jobs at once. It guarantees that every serving layer receives the columns it expects, and it prevents any column that was never meant to be public — such as a full date of birth or an internal identifier — from reaching a page by accident.


### Qualifiers and objections

There is a real risk of moving too early. A prototype that serves three people well does not need to become an application, and rebuilding it for hypothetical future users is a good way to waste weeks. The signals above are all observable, so it is reasonable to wait until at least one of them appears.

## Conclusion

The last mile decides how your work is judged, and the default choice, which is whichever tool you already know, is rarely the right one for every audience.

Start by identifying who uses the output and under what conditions. Choose the category of tool that matches, whether that is a script-based dashboard for internal exploration, an application framework for real users and real input, a static site for public and read-heavy products, or a business intelligence tool for self-service reporting. Then watch for the signals that you have outgrown your choice, and keep the logic in the data layer so switching stays cheap.

**Pick the tool per audience.**

Your pipeline's value is only visible in the last mile. Choose a serving layer that respects the people at the end of it.

As a first step, open the data product you maintain on a phone, on a normal connection, and time how long it takes to become useful. That number tells you whether your current serving layer matches your actual audience.

*This is the eleventh article in a series on data engineering lessons from building pipelines on external sources. The next article covers deployment and running costs, and how to keep a small platform cheap without making it fragile.*

**Tags:** Data Engineering, Data Products, Streamlit, Dashboards, Analytics Engineering
