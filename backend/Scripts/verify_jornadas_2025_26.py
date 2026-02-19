# scripts/verify_jornadas_2025_26.py
# Usage:
#   python scripts/verify_jornadas_2025_26.py 5884
#   python scripts/verify_jornadas_2025_26.py 5907

import sys
import re
import requests
from bs4 import BeautifulSoup

PARTIDOS_URL = "https://acb.com/es/partidos?competicion=1&jornada={jornada_id}"

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Extract the numeric game id from either:
# - https://live.acb.com/...-104666/previa
# - https://live.acb.com/...-104459/estadisticas
RX_LIVE_GAME_ID = re.compile(r"-([0-9]{5,})/(?:previa|resumen|estadisticas|preview|summary|stats)\b", re.IGNORECASE)

# The action anchor text we accept (only these are the "real game" links)
ACTION_TEXTS = {
    "previa", "resumen", "estadísticas", "estadisticas",
    "preview", "summary", "statistics", "stats",
}

def fetch(url: str) -> str:
    r = requests.get(url, headers=UA_HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def uniq_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def extract_from_matchcard(card) -> str | None:
    """
    Return the partido_id for THIS card by reading ONLY the "action" link:
    Previa / Resumen / Estadísticas (or EN equivalents).
    Ignore 'Precedentes' score links completely.
    """
    # Find anchors that look like the action button
    anchors = card.find_all("a", href=True)
    for a in anchors:
        txt = (a.get_text(" ", strip=True) or "").strip().lower()
        if txt in ACTION_TEXTS:
            href = a["href"]
            m = RX_LIVE_GAME_ID.search(href)
            if m:
                return m.group(1)

    # Fallback: sometimes the action is a <button> inside <a>, still same a.get_text()
    # If we didn't match by text, try: pick the FIRST live.acb.com link under "MatchActions"
    # (but still ignore precedents by requiring /previa|/resumen|/estadisticas)
    for a in anchors:
        href = a["href"]
        if "live.acb.com" not in href:
            continue
        m = RX_LIVE_GAME_ID.search(href)
        if m:
            return m.group(1)

    return None

def extract_partido_ids(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    # This is the list of cards shown for the jornada.
    # (Even if there are other sections, MatchCards are the unit we want.)
    cards = soup.select('div[class^="MatchCard_matchCard__"]')
    if not cards:
        return []

    ids = []
    for card in cards:
        pid = extract_from_matchcard(card)
        if pid:
            ids.append(pid)

    # There can be duplicated cards or extra UI cards; keep uniques.
    ids = uniq_keep_order(ids)

    # IMPORTANT:
    # Some pages can show extra cards outside the jornada list (e.g. other widgets).
    # If more than 9, keep the FIRST 9 encountered (jornada list appears first in DOM).
    if len(ids) > 9:
        ids = ids[:9]

    return ids

def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify_jornadas_2025_26.py <jornada_id>", flush=True)
        sys.exit(2)

    jornada_id = int(sys.argv[1])
    url = PARTIDOS_URL.format(jornada_id=jornada_id)
    html = fetch(url)

    ids = extract_partido_ids(html)

    print(f"URL: {url}", flush=True)
    print(f"Found partido_ids: {len(ids)}", flush=True)
    print("Sample:", ", ".join(ids[:12]), flush=True)

    if len(ids) != 9:
        print("WARNING: expected 9 partido_ids for a normal ACB round.", flush=True)

if __name__ == "__main__":
    main()
