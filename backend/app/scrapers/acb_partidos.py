# app/scrapers/acb_partidos.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

PARTIDOS_URL = "https://acb.com/es/partidos?competicion={competicion}&jornada={jornada_id}"

TEAM_ID_RE = re.compile(r"/club/plantilla/id/(\d+)(?:/|$)")
SCORE_RE = re.compile(r"^\s*(\d{1,3})\s*$")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

# Common date formats seen on sports sites:
# - "14/09/2025"
# - "14/09" (we may need to infer year)
DATE_DDMMYYYY_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
DATE_DDMM_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")

try:
    TZ = ZoneInfo("Europe/Madrid")
except Exception:
    TZ = None  # fallback if tzdata is missing

# Example text seen on live.acb.com:
# "Wednesday 18 February 2026 20:00"
LIVE_DT_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*"
    r"(?:·\s*)?\d{1,2}:\d{2}\b",
    re.I,
)


LIVE_ACB_RE = re.compile(r"^https?://live\.acb\.com/partidos/.+/(?:previa|resumen)$", re.I)



@dataclass(frozen=True)
class ParsedFixture:
    home_team_id: str
    away_team_id: str
    kickoff_at: Optional[datetime]
    is_finished: bool
    home_score: Optional[int]
    away_score: Optional[int]
    is_postponed: bool
    is_advanced: bool
    source_url: str


def _extract_team_id_from_href(href: str) -> Optional[str]:
    m = TEAM_ID_RE.search(href or "")
    return m.group(1) if m else None


def _is_matchcard_div(tag) -> bool:
    if tag.name != "div":
        return False
    classes = tag.get("class") or []
    return any(isinstance(c, str) and c.startswith("MatchCard_matchCard__") for c in classes)


def _infer_year_for_ddmm(season_id: str, month: int) -> int:
    """
    season_id like "2025-26".
    If month is Aug-Dec -> start year (2025)
    If month is Jan-Jul -> end year (2026)
    """
    try:
        y0 = int(season_id.split("-")[0])
        y1 = y0 + 1
    except Exception:
        # fallback: current-ish assumption
        y0 = datetime.now().year
        y1 = y0 + 1

    return y0 if month >= 8 else y1


def _parse_kickoff_from_text(season_id: str, text: str) -> Optional[datetime]:
    """
    Try to find a date + time somewhere inside the card text.
    If none, return None.
    """
    # Full date
    m = DATE_DDMMYYYY_RE.search(text)
    if m:
        d = int(m.group(1))
        mon = int(m.group(2))
        y = int(m.group(3))
        tm = TIME_RE.search(text)
        if tm:
            hh = int(tm.group(1))
            mm = int(tm.group(2))
            return datetime(y, mon, d, hh, mm)
        return datetime(y, mon, d)

    # dd/mm (infer year)
    m2 = DATE_DDMM_RE.search(text)
    if m2:
        d = int(m2.group(1))
        mon = int(m2.group(2))
        y = _infer_year_for_ddmm(season_id, mon)
        tm = TIME_RE.search(text)
        if tm:
            hh = int(tm.group(1))
            mm = int(tm.group(2))
            return datetime(y, mon, d, hh, mm)
        return datetime(y, mon, d)

    return None

def _extract_live_match_url(card) -> Optional[str]:
    hrefs = []
    for a in card.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href:
            hrefs.append(href)

    # prefer previa
    for href in hrefs:
        if "live.acb.com/partidos/" in href.lower() and href.lower().endswith("/previa"):
            return href

    # then resumen
    for href in hrefs:
        if "live.acb.com/partidos/" in href.lower() and href.lower().endswith("/resumen"):
            return href

    # any other live match link
    for href in hrefs:
        if LIVE_ACB_RE.match(href):
            return href

    return None

def _looks_like_skeleton_datetime(card_text: str) -> bool:
    """
    Detect the '--- -- ---' and '--:--' placeholders you pasted.
    """
    return ("---" in card_text) or ("--:--" in card_text)


def scrape_partidos(
    *,
    season_id: str,
    competicion: int,
    jornada_id: int,
    timeout_s: float = 30.0,
) -> List[ParsedFixture]:
    url = PARTIDOS_URL.format(competicion=competicion, jornada_id=jornada_id)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://acb.com/",
        "Connection": "keep-alive",
    }

    with httpx.Client(headers=headers, timeout=timeout_s, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    cards_all = soup.find_all(_is_matchcard_div)
    # keep only the outermost match cards (no parent matchcard)
    cards = [c for c in cards_all if not c.find_parent(_is_matchcard_div)]
    
    fixtures: List[ParsedFixture] = []

    for card in cards:
        # Team links (usually 2)
        team_links = card.find_all("a", href=TEAM_ID_RE)
        team_ids: List[str] = []
        for a in team_links:
            tid = _extract_team_id_from_href(a.get("href", ""))
            if tid and tid not in team_ids:
                team_ids.append(tid)
            if len(team_ids) == 2:
                break
        if len(team_ids) != 2:
            continue

        home_id, away_id = team_ids[0], team_ids[1]

        # Finished?
        card_text = card.get_text(" ", strip=True)
        is_finished = "Final" in card_text  # robust enough for now

        # Scores: MatchScore_matchScore__... contains numbers (we pick first 2 ints)
        score_nodes = card.find_all("p", class_=re.compile(r"^MatchScore_matchScore__"))
        scores: List[int] = []
        for n in score_nodes:
            t = n.get_text(strip=True)
            ms = SCORE_RE.match(t)
            if ms:
                scores.append(int(ms.group(1)))
            if len(scores) == 2:
                break

        home_score = scores[0] if len(scores) >= 1 else None
        away_score = scores[1] if len(scores) >= 2 else None

        # Postponed / advanced flags (look for keywords)
        up_text = card_text.upper()
        is_postponed = False
        is_advanced = False

        kickoff_at = _parse_kickoff_from_text(season_id, card_text)

        live_url = _extract_live_match_url(card)

        # If ACB card doesn't have a real datetime (skeleton / none), try live.acb.com
        if kickoff_at is None and live_url:
            kickoff_at = fetch_kickoff_from_live(live_url)


        fixtures.append(
            ParsedFixture(
                home_team_id=home_id,
                away_team_id=away_id,
                kickoff_at=kickoff_at,
                is_finished=is_finished,
                home_score=home_score,
                away_score=away_score,
                is_postponed=is_postponed,
                is_advanced=is_advanced,
                source_url=url,
            )
        )

    return fixtures

DDMMYYYY_HHMM_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})\b")

ISO_DT_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\b")

LIVE_DT_RE_2 = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4}).{0,20}?(\d{1,2}):(\d{2})\b",
    re.I,
)

def fetch_kickoff_from_live(url: str, timeout_s: float = 30.0) -> Optional[datetime]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en,en-GB;q=0.9,es;q=0.8",
    }

    with httpx.Client(headers=headers, timeout=timeout_s, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        html = r.text

    soup = BeautifulSoup(html, "lxml")

    # 1) Try <time datetime="...">
    t = soup.find("time")
    if t and t.get("datetime"):
        dt = dtparser.parse(t["datetime"])
        return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)

    # 2) Try ISO-like datetime inside the page
    m = ISO_DT_RE.search(html)
    if m:
        dt = dtparser.parse(m.group(1))
        return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)

    # 3) Fallback: English “18 February 2026 … 20:00” style (weekday optional)
    text = soup.get_text("\n", strip=True)

    m = LIVE_DT_RE.search(text)
    if m:
        dt = dtparser.parse(m.group(0), fuzzy=True)
        return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)

    m2 = LIVE_DT_RE_2.search(text)
    if m2:
        dt = dtparser.parse(m2.group(0), fuzzy=True)
        return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)

    return None
