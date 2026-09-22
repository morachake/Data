"""
RegistrySpider — base class for all production spiders.

Responsibilities
----------------
- Loads the registry once on construction.
- Enforces the ``allowed: true`` flag from sources.yml before any requests
  are yielded.
- Accepts ``league_id`` and ``season`` Scrapy CLI arguments so Dagster can
  run one partition at a time:

      scrapy crawl wikipedia_season -a league_id=RSA_PREM -a season=2024-25

- Exposes ``self.active_leagues`` as the list of leagues this spider should
  cover in a full (unpartitioned) run.
- Sets ``download_delay`` from the source's ``rate_limit_seconds`` config.

Subclass contract
-----------------
Every subclass must set the class attribute ``source_id`` matching an entry
in config/sources.yml, and must only yield ``RawPageItem`` instances.
"""

import scrapy

from ingestion.registry import get_registry


class RegistrySpider(scrapy.Spider):
    # Subclasses must override this.
    source_id: str = ""

    def __init__(self, league_id: str | None = None, season: str | None = None, **kwargs):
        super().__init__(**kwargs)

        self.registry = get_registry()

        if not self.source_id:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set `source_id` as a class attribute."
            )

        # Enforce the allowed flag — raises immediately if the source is blocked.
        self.registry.enforce_allowed(self.source_id)

        # Override download_delay from source config.
        src = self.registry.get_source(self.source_id)
        rate = src.get("rate_limit_seconds", 1.0)
        self.custom_settings = {**(self.custom_settings or {}), "DOWNLOAD_DELAY": rate}

        # Partition filter: if league_id/season are given, restrict to that pair.
        self.league_id: str | None = league_id
        self.season: str | None = season

    @property
    def active_leagues(self) -> list[dict]:
        """
        Leagues that use this source and have at least one season configured.
        If self.league_id is set, returns only that league (for partitioned runs).
        """
        leagues = self.registry.get_active_leagues_for_source(self.source_id)
        if self.league_id:
            return [lg for lg in leagues if lg["league_id"] == self.league_id]
        return leagues

    @property
    def active_partitions(self) -> list[tuple[str, str]]:
        """
        (league_id, season) pairs this spider run covers.
        If both league_id and season are provided, returns exactly one pair.
        """
        pairs: list[tuple[str, str]] = []
        for lg in self.active_leagues:
            seasons = lg.get("seasons", [])
            if self.season:
                if self.season in seasons:
                    pairs.append((lg["league_id"], self.season))
            else:
                for s in seasons:
                    pairs.append((lg["league_id"], s))
        return pairs
