import socket

from urllib.parse import quote

import scrapy

from ingestion.clubs import CLUB_WIKI_TITLES
from ingestion.player_extract import (
    appearance_table_rows,
    career_rows,
    extract_injuries,
    extract_squad_players,
    first_bio,
    infobox_image,
    infobox_map,
    is_likely_player_title,
    looks_like_footballer,
    looks_like_squad_table,
    wiki_title_from_href,
    wikidata_id,
)
from ingestion.spiders.wiki_psl_seasons import seasons_through_current

_ORIG_GETADDRINFO = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _ORIG_GETADDRINFO(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_getaddrinfo


class WikiPslPlayersSpider(scrapy.Spider):
    name = "wiki_psl_players"
    allowed_domains = ["en.wikipedia.org"]
    handle_httpstatus_list = [404]
    custom_settings = {
        "FEEDS": {
            "../data/raw/%(name)s/%(time)s.jsonl": {"format": "jsonlines", "encoding": "utf8"},
        },
        "RETRY_TIMES": 4,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_players: set[str] = set()

    async def start(self):
        seasons = seasons_through_current()
        for team_id, titles in CLUB_WIKI_TITLES.items():
            wiki_title = titles[0]
            yield scrapy.Request(
                self._wiki_url(wiki_title),
                callback=self.parse_club,
                cb_kwargs={"team_id": team_id, "season": None, "club_title": wiki_title},
            )
            yield scrapy.Request(
                self._wiki_url(f"Category:{wiki_title} players"),
                callback=self.parse_category,
                cb_kwargs={"team_id": team_id, "club_title": wiki_title},
            )
            for season in seasons:
                yield scrapy.Request(
                    self._wiki_url(f"{season} {wiki_title} season"),
                    callback=self.parse_club,
                    cb_kwargs={"team_id": team_id, "season": season, "club_title": wiki_title},
                )

    def parse_category(self, response, team_id, club_title):
        if response.status == 404:
            return
        for href in response.css("#mw-pages a::attr(href)").getall():
            title = wiki_title_from_href(href)
            if not is_likely_player_title(title) or title in self.seen_players:
                continue
            self.seen_players.add(title)
            yield scrapy.Request(
                self._wiki_url(title),
                callback=self.parse_player,
                cb_kwargs={
                    "discovered_from": response.url,
                    "team_id": team_id,
                    "season": None,
                },
            )
        next_href = response.xpath(
            "//div[@id='mw-pages']//a[contains(normalize-space(.), 'next page')]/@href"
        ).get()
        if next_href:
            yield response.follow(
                next_href,
                callback=self.parse_category,
                cb_kwargs={"team_id": team_id, "club_title": club_title},
            )

    def parse_club(self, response, team_id, season, club_title):
        if response.status == 404:
            return
        for table in response.css("table"):
            rows = appearance_table_rows(table)
            if len(rows) < 2:
                continue
            header = rows[0]
            if not looks_like_squad_table(header):
                continue
            players = extract_squad_players(table, header, rows)
            yield {
                "kind": "squad_table",
                "team_id": team_id,
                "season": season,
                "club_title": club_title,
                "source_url": response.url,
                "header": header,
                "rows": rows,
                "players": players,
            }
            for player in players:
                title = player.get("wiki_title")
                if not is_likely_player_title(title) or title in self.seen_players:
                    continue
                self.seen_players.add(title)
                yield scrapy.Request(
                    self._wiki_url(title),
                    callback=self.parse_player,
                    cb_kwargs={"discovered_from": response.url, "team_id": team_id, "season": season},
                )

    def parse_player(self, response, discovered_from, team_id, season):
        if response.status == 404:
            return
        heading = " ".join(response.css("h1#firstHeading ::text").getall()).strip()
        title = heading or response.url.rsplit("/", 1)[-1].replace("_", " ")
        if not is_likely_player_title(title):
            return
        info = infobox_map(response)
        career = career_rows(response)
        bio = first_bio(response)
        if "founded" in info or "ground" in info:
            return
        if not looks_like_footballer(info, bio, career):
            return
        body = " ".join(
            response.css("div.mw-parser-output p::text, div.mw-parser-output p *:not(sup)::text").getall()
        )
        yield {
            "kind": "player_profile",
            "wiki_title": title,
            "source_url": response.url,
            "discovered_from": discovered_from,
            "discovered_team_id": team_id,
            "discovered_season": season,
            "wikidata_id": wikidata_id(response),
            "image_url": infobox_image(response),
            "bio": bio,
            "infobox": info,
            "career": career,
            "injuries": extract_injuries(body),
        }

    def _wiki_url(self, title: str) -> str:
        return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
