"""
Scrapy item pipelines.

Pipeline order (set in settings.py ITEM_PIPELINES):
  1. ValidateItemPipeline   – drop items missing required fields
  2. RawWriterPipeline      – write items to Hive-partitioned JSONL files
  3. RunStatsPipeline       – count items/errors; log on spider close

The RawWriterPipeline replaces the FEEDS setting for RawPageItem spiders.
It writes:
  data/raw/source=<source_id>/league=<league_id>/season=<season>/
           run=<timestamp>_<run_id_prefix>.jsonl

and a companion manifest at:
  data/raw/_manifests/<run_id>.json

Legacy spiders (wiki_psl_players) keep their own FEEDS custom_settings and
do NOT emit RawPageItem, so they are untouched by these pipelines.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from scrapy.exceptions import DropItem

from ingestion.items import RawPageItem

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw"


class ValidateItemPipeline:
    REQUIRED_FIELDS = {
        "source_id",
        "league_id",
        "season",
        "url",
        "block_type",
        "payload",
        "fetched_at",
    }

    def process_item(self, item, spider):
        if not isinstance(item, RawPageItem):
            # Pass non-RawPageItem items through untouched (legacy spiders).
            return item
        missing = self.REQUIRED_FIELDS - set(k for k in item.keys() if item.get(k) is not None)
        if missing:
            raise DropItem(f"RawPageItem missing required fields: {sorted(missing)}")
        return item


class RawWriterPipeline:
    def open_spider(self, spider):
        self._run_id = str(uuid.uuid4())
        self._start = datetime.now(timezone.utc)
        self._items = 0
        self._errors = 0
        self._open_files: dict[str, object] = {}
        # Expose run_id on the spider so other pipelines and callbacks can read it.
        spider.run_id = self._run_id

    def _file_for(self, item: RawPageItem):
        key = (item["source_id"], item["league_id"], item["season"])
        if key not in self._open_files:
            folder = (
                RAW_ROOT
                / f"source={item['source_id']}"
                / f"league={item['league_id']}"
                / f"season={item['season']}"
            )
            folder.mkdir(parents=True, exist_ok=True)
            ts = self._start.strftime("%Y-%m-%dT%H-%M-%S+00-00")
            path = folder / f"run={ts}_{self._run_id[:8]}.jsonl"
            self._open_files[key] = path.open("a", encoding="utf-8")
        return self._open_files[key]

    def process_item(self, item, spider):
        if not isinstance(item, RawPageItem):
            return item

        # Stamp the run_id onto every item.
        item["run_id"] = self._run_id

        # Compute content_hash if the spider didn't set one.
        if not item.get("content_hash"):
            raw = json.dumps(item.get("payload"), sort_keys=True, default=str)
            item["content_hash"] = hashlib.md5(raw.encode()).hexdigest()

        fh = self._file_for(item)
        fh.write(json.dumps(dict(item), default=str) + "\n")
        self._items += 1
        return item

    def close_spider(self, spider):
        for fh in self._open_files.values():
            fh.close()

        # Write run manifest.
        manifests = RAW_ROOT / "_manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        elapsed = (datetime.now(timezone.utc) - self._start).total_seconds()
        manifest = {
            "run_id": self._run_id,
            "spider": spider.name,
            "source_id": getattr(spider, "source_id", None),
            "league_id": getattr(spider, "league_id", None),
            "season": getattr(spider, "season", None),
            "items": self._items,
            "errors": self._errors,
            "duration_seconds": round(elapsed, 2),
            "started_at": self._start.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        (manifests / f"{self._run_id}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )


class RunStatsPipeline:
    def open_spider(self, spider):
        self._items = 0

    def process_item(self, item, spider):
        if isinstance(item, RawPageItem):
            self._items += 1
        return item

    def close_spider(self, spider):
        spider.logger.info("RunStatsPipeline: %d RawPageItems emitted", self._items)
