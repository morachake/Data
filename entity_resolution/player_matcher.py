"""
entity_resolution/player_matcher.py

Block → Score → Decide → Record pipeline for player identity resolution.

Thresholds (tunable)
--------------------
HIGH   ≥ 92  → auto-accept (write to core.player_alias)
LOW    < 75  → auto-reject
GREY   75–91 → send to staging.review_queue for human review

DOB confidence rules
--------------------
- high:    exact date from two independent sources
- medium:  exact date from one source, or year+month only from two sources
- low:     year only, or date from one source only
- unknown: no DOB in any source

Usage
-----
    matcher = PlayerMatcher(conn)
    matcher.resolve_season(league_id="RSA_PREM", season="2024-25")
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Optional

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

from entity_resolution.name_normalise import blocking_key, canonical, token_overlap

THRESHOLD_HIGH = 92
THRESHOLD_LOW = 75


@dataclass
class PlayerCandidate:
    player_raw: str
    team_raw: str
    source_id: str
    season: str
    league_id: str
    nationality: Optional[str] = None
    dob_raw: Optional[str] = None
    position_raw: Optional[str] = None


@dataclass
class MatchDecision:
    candidate_a: PlayerCandidate
    candidate_b: PlayerCandidate
    score: float
    method: str                # "auto_accept" | "auto_reject" | "review_queue"
    player_id: Optional[str] = None  # assigned on accept


def _fuzzy_score(a: str, b: str) -> float:
    """Return a 0-100 similarity score between two strings."""
    if not _HAS_RAPIDFUZZ:
        # Fallback: simple token overlap * 100
        return token_overlap(a, b) * 100
    canon_a = canonical(a)
    canon_b = canonical(b)
    return fuzz.WRatio(canon_a, canon_b)


def _dob_score(dob_a: Optional[str], dob_b: Optional[str]) -> float:
    """
    Bonus points for matching DOB:
      +15  exact date match
      +10  year match only
       0   one or both missing
    """
    if not dob_a or not dob_b:
        return 0.0
    if dob_a[:10] == dob_b[:10]:
        return 15.0
    if dob_a[:4] == dob_b[:4]:
        return 10.0
    # Conflicting DOB — penalise slightly
    if len(dob_a) >= 4 and len(dob_b) >= 4:
        return -5.0
    return 0.0


def _dob_confidence(dobs: list[Optional[str]]) -> str:
    """
    Given a list of DOB values (across sources), determine confidence.
    """
    clean = [d for d in dobs if d]
    if not clean:
        return "unknown"
    # Check exact date format (YYYY-MM-DD)
    full_dates = [d for d in clean if len(d) >= 10 and d[4] == "-"]
    if len(set(full_dates)) == 1 and len(full_dates) >= 2:
        return "high"
    if len(full_dates) >= 1:
        return "medium"
    # Year only
    years = [d[:4] for d in clean if len(d) >= 4]
    if len(set(years)) == 1 and len(years) >= 2:
        return "medium"
    return "low"


class PlayerMatcher:
    def __init__(self, db_conn=None):
        """
        db_conn: optional psycopg connection for writing results.
        If None, operate in dry-run mode (return decisions without writing).
        """
        self.conn = db_conn

    def match_candidates(
        self, candidates: list[PlayerCandidate]
    ) -> list[MatchDecision]:
        """
        Block candidates by blocking_key, score pairs, decide disposition.
        Returns list of MatchDecision objects.
        """
        # Group by blocking key
        blocks: dict[str, list[PlayerCandidate]] = {}
        for c in candidates:
            key = blocking_key(c.player_raw)
            blocks.setdefault(key, []).append(c)

        decisions: list[MatchDecision] = []
        for key, group in blocks.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    if a.source_id == b.source_id:
                        continue  # same source — skip
                    score = _fuzzy_score(a.player_raw, b.player_raw)
                    score += _dob_score(a.dob_raw, b.dob_raw)
                    score = min(score, 100.0)

                    if score >= THRESHOLD_HIGH:
                        method = "auto_accept"
                        player_id = str(uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            canonical(a.player_raw)
                        ))
                    elif score < THRESHOLD_LOW:
                        method = "auto_reject"
                        player_id = None
                    else:
                        method = "review_queue"
                        player_id = None

                    decisions.append(MatchDecision(
                        candidate_a=a,
                        candidate_b=b,
                        score=score,
                        method=method,
                        player_id=player_id,
                    ))

        return decisions

    def resolve_season(
        self, league_id: str, season: str
    ) -> list[MatchDecision]:
        """
        Load squad/appearance candidates for a season, run matching,
        write results to DB (if conn provided).
        """
        if not self.conn:
            raise RuntimeError("No DB connection — initialise PlayerMatcher with a psycopg conn.")

        candidates = self._load_candidates(league_id, season)
        decisions = self.match_candidates(candidates)
        self._write_decisions(decisions)
        return decisions

    def _load_candidates(self, league_id: str, season: str) -> list[PlayerCandidate]:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT player_raw, team_raw, source_id, league_id, season,
                       nationality_raw, null::text as dob_raw, position_raw
                FROM staging.stg_squad
                WHERE league_id = %s AND season = %s
            """, (league_id, season))
            rows = cur.fetchall()
        return [
            PlayerCandidate(
                player_raw=r[0], team_raw=r[1], source_id=r[2],
                league_id=r[3], season=r[4], nationality=r[5],
                dob_raw=r[6], position_raw=r[7],
            )
            for r in rows
        ]

    def _write_decisions(self, decisions: list[MatchDecision]) -> None:
        accepts = [d for d in decisions if d.method == "auto_accept"]
        reviews = [d for d in decisions if d.method == "review_queue"]

        with self.conn.cursor() as cur:
            # Write accepted aliases
            for d in accepts:
                for cand in (d.candidate_a, d.candidate_b):
                    cur.execute("""
                        INSERT INTO core.player_alias
                            (alias, source_id, player_id, method, score, resolved_at)
                        VALUES (%s, %s, %s, %s, %s, now())
                        ON CONFLICT (alias, source_id) DO UPDATE
                            SET player_id = EXCLUDED.player_id,
                                score = EXCLUDED.score,
                                resolved_at = now()
                    """, (
                        cand.player_raw,
                        cand.source_id,
                        d.player_id,
                        d.method,
                        d.score,
                    ))

            # Write grey-zone to review queue
            for d in reviews:
                cur.execute("""
                    INSERT INTO staging.review_queue
                        (name_a, source_a, name_b, source_b, score, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'pending', now())
                    ON CONFLICT DO NOTHING
                """, (
                    d.candidate_a.player_raw,
                    d.candidate_a.source_id,
                    d.candidate_b.player_raw,
                    d.candidate_b.source_id,
                    d.score,
                ))
        self.conn.commit()
