# app/scrapers/acb_calendario.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple

import httpx
from bs4 import BeautifulSoup

CALENDARIO_URL = "https://www.acb.com/es/calendario?temporada={temporada}"

TEAM_ID_RE = re.compile(r"/club/plantilla/id/(\d+)(?:/|$)")

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DATE_RE = re.compile(r"^\s*(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})\s*$", re.I)
TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")
SCORE_RE = re.compile(r"\b(\d{1,3})\s*-\s*(\d{1,3})\b")

JORNADA_RE = re.compile(r"Jornada\s+(\d+)", re.I)

@dataclass(frozen=True)
class ParsedFixture:
    round_number: int
    home_team_id: str
    away_team_id: str
    kickoff_at: Optional[datetime]
    is_finished: bool
    home_score: Optional[int]
    away_score: Optional[int]
    is_postponed: bool
    is_advanced: bool
    source_url: str


def _parse_es_date(date_text: str) -> Optional[Tuple[int, int, int]]:
    m = DATE_RE.match(date_text.strip().lower())
    if not m:
        return None
    d = int(m.group(1))
    mon_name = m.group(2).strip().lower()
    y = int(m.group(3))
    mon = MONTHS_ES.get(mon_name)
    if not mon:
        return None
    return (y, mon, d)


def _parse_time(time_text: str) -> Optional[Tuple[int, int]]:
    t = time_text.strip().upper()
    if t == "XX:XX":
        return None
    m = TIME_RE.match(t)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def _extract_team_id(a_tag) -> Optional[str]:
    href = a_tag.get("href") or ""
    m = TEAM_ID_RE.search(href)
    return m.group(1) if m else None


def _nearest_previous_jornada_number(block) -> Optional[int]:
    s = block.find_previous(string=JORNADA_RE)
    if not s:
        return None
    m = JORNADA_RE.search(str(s))
    return int(m.group(1)) if m else None


def _nearest_previous_date(block) -> Optional[Tuple[int, int, int]]:
    # Walk backwards through text nodes until we find a Spanish long date line
    node = block
    for _ in range(300):  # bounded so we never go crazy
        node = node.find_previous(string=True)
        if not node:
            return None
        dp = _parse_es_date(str(node))
        if dp:
            return dp
    return None


def scrape_calendario(temporada: int, timeout_s: float = 30.0) -> List[ParsedFixture]:
    url = CALENDARIO_URL.format(temporada=temporada)

    with httpx.Client(
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
        timeout=timeout_s,
        follow_redirects=True,
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        print("DEBUG status:", r.status_code)
        print("DEBUG len(html):", len(r.text))
        print("DEBUG has /club/plantilla/id:", "/club/plantilla/id/" in r.text)
        print("DEBUG has 'Jornada 1':", "Jornada 1" in r.text)
        print("DEBUG title snippet:", r.text[:200].replace("\n", " ")[:200])

    soup = BeautifulSoup(r.text, "lxml")

    # 1) Find match blocks: nodes that contain exactly 2 team links.
    #    We start from each team link and climb to a “small” parent that has the pair.
    fixtures: List[ParsedFixture] = []
    seen_blocks = set()

    team_links_all = soup.find_all("a", href=TEAM_ID_RE)
    if not team_links_all:
        return []

    for a in team_links_all:
        block = a
        for _ in range(8):
            if not block or not hasattr(block, "find_all"):
                break
            links_in = block.find_all("a", href=TEAM_ID_RE)
            if len(links_in) == 2:
                break
            block = block.parent

        if not block or not hasattr(block, "find_all"):
            continue

        # Dedup by object identity
        bid = id(block)
        if bid in seen_blocks:
            continue

        links_in = block.find_all("a", href=TEAM_ID_RE)
        if len(links_in) != 2:
            continue

        home_a, away_a = links_in[0], links_in[1]
        home_id = _extract_team_id(home_a)
        away_id = _extract_team_id(away_a)
        if not home_id or not away_id or home_id == away_id:
            continue

        seen_blocks.add(bid)

        # 2) Round number: nearest previous “Jornada N”
        round_number = _nearest_previous_jornada_number(block)
        if round_number is None:
            # Without jornada, we can’t safely store this record.
            continue

        # 3) Date/time
        date_parts = _nearest_previous_date(block)

        # time usually appears inside the block (or as XX:XX)
        time_parts: Optional[Tuple[int, int]] = None
        block_lines = [t.strip() for t in block.get_text("\n", strip=True).split("\n") if t.strip()]
        has_xx = any(line.strip().upper() == "XX:XX" for line in block_lines)
        for line in block_lines:
            tp = _parse_time(line)
            if tp:
                time_parts = tp
                break

        kickoff_at: Optional[datetime] = None
        if date_parts:
            y, mon, d = date_parts
            if time_parts:
                hh, mm = time_parts
                kickoff_at = datetime(y, mon, d, hh, mm)
            elif has_xx:
                kickoff_at = None

        # 4) Scores / finished
        block_text = block.get_text(" ", strip=True)
        sm = SCORE_RE.search(block_text)
        if sm:
            home_score = int(sm.group(1))
            away_score = int(sm.group(2))
            is_finished = True
        else:
            home_score = None
            away_score = None
            is_finished = False

        # 5) Postponed / advanced (best-effort from text)
        low = block_text.lower()
        is_postponed = ("aplaz" in low) or ("suspend" in low)
        is_advanced = ("adelant" in low)

        fixtures.append(
            ParsedFixture(
                round_number=round_number,
                home_team_id=str(home_id),
                away_team_id=str(away_id),
                kickoff_at=kickoff_at,
                is_finished=is_finished,
                home_score=home_score,
                away_score=away_score,
                is_postponed=is_postponed,
                is_advanced=is_advanced,
                source_url=url,
            )
        )

    # Optional: stable ordering (round, kickoff, teams)
    fixtures.sort(
        key=lambda fx: (
            fx.round_number,
            fx.kickoff_at or datetime(1970, 1, 1),
            fx.home_team_id,
            fx.away_team_id,
        )
    )
    return fixtures
