"""
Registry — loads config/leagues.yml and config/sources.yml once and exposes
helper methods used by spiders and pipelines.

Rule: spiders call ``registry.enforce_allowed(source_id)`` before yielding
any request.  If the source has ``allowed: false`` in sources.yml the spider
raises RuntimeError immediately rather than crawling silently.
"""

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

_REGISTRY: "Registry | None" = None


class Registry:
    def __init__(self) -> None:
        self.leagues: dict[str, dict[str, Any]] = {}
        self.sources: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        leagues_path = CONFIG_DIR / "leagues.yml"
        sources_path = CONFIG_DIR / "sources.yml"

        if not leagues_path.exists():
            raise FileNotFoundError(f"Missing config file: {leagues_path}")
        if not sources_path.exists():
            raise FileNotFoundError(f"Missing config file: {sources_path}")

        with leagues_path.open(encoding="utf-8") as f:
            raw_leagues = yaml.safe_load(f)
        with sources_path.open(encoding="utf-8") as f:
            raw_sources = yaml.safe_load(f)

        self.leagues = {lg["league_id"]: lg for lg in raw_leagues.get("leagues", [])}
        self.sources = {s["source_id"]: s for s in raw_sources.get("sources", [])}

    # ------------------------------------------------------------------ #
    # Source helpers
    # ------------------------------------------------------------------ #

    def get_source(self, source_id: str) -> dict[str, Any]:
        if source_id not in self.sources:
            raise KeyError(f"Unknown source_id '{source_id}'. Add it to config/sources.yml.")
        return self.sources[source_id]

    def enforce_allowed(self, source_id: str) -> None:
        """Raise RuntimeError if the source is not marked allowed: true."""
        src = self.get_source(source_id)
        if not src.get("allowed", False):
            raise RuntimeError(
                f"Source '{source_id}' is not allowed to be scraped. "
                "Complete a source audit, then set allowed: true in config/sources.yml."
            )

    # ------------------------------------------------------------------ #
    # League helpers
    # ------------------------------------------------------------------ #

    def get_league(self, league_id: str) -> dict[str, Any]:
        if league_id not in self.leagues:
            raise KeyError(f"Unknown league_id '{league_id}'. Add it to config/leagues.yml.")
        return self.leagues[league_id]

    def get_leagues_for_source(self, source_id: str) -> list[dict[str, Any]]:
        """Return all leagues whose sources list includes source_id."""
        return [
            lg for lg in self.leagues.values()
            if source_id in lg.get("sources", [])
        ]

    def get_active_leagues_for_source(self, source_id: str) -> list[dict[str, Any]]:
        """Return leagues with source_id and at least one season defined."""
        return [
            lg for lg in self.get_leagues_for_source(source_id)
            if lg.get("seasons")
        ]

    # ------------------------------------------------------------------ #
    # All league × season partitions for a given source
    # ------------------------------------------------------------------ #

    def partitions(self, source_id: str) -> list[tuple[str, str]]:
        """Return (league_id, season) pairs for active leagues that use source_id."""
        result = []
        for lg in self.get_active_leagues_for_source(source_id):
            for season in lg["seasons"]:
                result.append((lg["league_id"], season))
        return result


def get_registry() -> Registry:
    """Return the singleton Registry, creating it on first call."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = Registry()
    return _REGISTRY
