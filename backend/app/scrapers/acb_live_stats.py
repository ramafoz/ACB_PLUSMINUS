from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

# KEEP THE CONSTANT NAME for drop-in compatibility with existing imports.
# It now points to OFFICIAL FINAL stats (acb.com), not live.acb.com.
LIVE_STATS_URL = "https://acb.com/partido/estadisticas/id/{game_id}"


def _mmss_to_seconds(mmss: str | None) -> int | None:
    """
    Drop-in compatible helper.
    Supports formats like:
      "05:26", "12:24", "200:00" (totals row, though we skip totals anyway)
    Returns seconds, or None if empty / invalid.
    """
    if not mmss:
        return None
    mmss = mmss.strip()
    if not mmss or mmss == "\xa0":
        return None

    m = re.match(r"^\s*(\d{1,3}):(\d{2})\s*$", mmss)
    if not m:
        return None

    minutes = int(m.group(1))
    seconds = int(m.group(2))
    return minutes * 60 + seconds


def fetch_live_stats_html(game_id: str, timeout: float = 20.0) -> str:
    """
    Drop-in compatible name.
    Fetches OFFICIAL FINAL stats HTML from acb.com (not live.acb.com).
    """
    url = LIVE_STATS_URL.format(game_id=game_id)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def _clean_text(node) -> str:
    if node is None:
        return ""
    txt = node.get_text(strip=True)
    return "" if txt == "\xa0" else txt


def _extract_acb_player_id(href: str) -> str | None:
    """
    Examples:
      /jugador/ver/20212243-O. Balcerowski.html
      /jugador/ver/30004013-M.-Normantas
    """
    m = re.search(r"/jugador/ver/(\d+)-", href or "")
    return m.group(1) if m else None


def parse_minutes_plusminus(html: str) -> list[dict]:
    """
    Drop-in compatible return schema (same keys as your current live scraper):
      - acb_player_id: str
      - play_time: str | None
      - minutes_seconds: int | None
      - plus_minus: int | None
      - is_started: bool | None

    Parses OFFICIAL FINAL stats from acb.com HTML tables.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []

    # Two team sections:
    # - Home: section.partido (not .visitante)
    # - Away: section.partido.visitante
    sections = [
        soup.select_one("section.partido:not(.visitante)"),
        soup.select_one("section.partido.visitante"),
    ]

    for sec in sections:
        if not sec:
            continue

        table = sec.select_one("table[data-toggle='table-estadisticas']")
        if not table:
            continue

        # Find the header row that contains the actual column names (Min, +/-)
        header: list[str] | None = None
        for tr in table.select("thead tr"):
            ths = [th.get_text(strip=True) for th in tr.find_all("th")]
            if "Min" in ths and "+/-" in ths:
                header = ths
                break
        if not header:
            continue

        col_min = header.index("Min")
        col_pm = header.index("+/-")

        for tr in table.select("tbody tr"):
            classes = tr.get("class", [])

            # Skip non-player rows
            if "equipo" in classes or "totales" in classes:
                continue
            if tr.select_one("td.nombre.entrenador") or tr.select_one("td.nombre_eliminados5f"):
                continue

            a = tr.select_one("td.nombre.jugador a[href^='/jugador/ver/']")
            if not a:
                continue

            acb_player_id = _extract_acb_player_id(a.get("href", ""))
            if not acb_player_id:
                continue

            tds = tr.find_all("td")
            if len(tds) <= max(col_min, col_pm):
                continue

            # Starters are marked with '*' in dorsal cell (e.g. "*0", "*2")
            dorsal_txt = _clean_text(tr.select_one("td.dorsal"))
            is_started = True if dorsal_txt.startswith("*") else False

            play_time = _clean_text(tds[col_min]) or None
            pm_txt = _clean_text(tds[col_pm])

            minutes_seconds = _mmss_to_seconds(play_time) if play_time else None

            plus_minus = None
            if pm_txt:
                try:
                    plus_minus = int(pm_txt)
                except ValueError:
                    plus_minus = None

            out.append(
                {
                    "acb_player_id": str(acb_player_id),
                    "play_time": play_time,
                    "minutes_seconds": minutes_seconds,
                    "plus_minus": plus_minus,
                    "is_started": is_started,
                }
            )

    # Deduplicate by player id (keep last) — same behavior as your existing file.
    uniq: dict[str, dict] = {}
    for row in out:
        uniq[row["acb_player_id"]] = row
    return list(uniq.values())