from typing import Dict, Any, List
import re
from html import unescape

from app.scrapers.http import make_client


def fetch_team_roster_html(acb_club_id: str, season_id: str, include_html: bool = False) -> Dict[str, Any]:
    url = f"https://www.acb.com/club/plantilla-lista/id/{acb_club_id}/temporada_id/{season_id}"
    with make_client() as client:
        resp = client.get(url)

        data: Dict[str, Any] = {
            "requested_url": url,
            "final_url": str(resp.url),
            "status_code": resp.status_code,
            "html_len": len(resp.text or ""),
        }

        if include_html:
            data["html"] = resp.text or ""

        return data

    
def parse_roster_players(html: str) -> List[Dict[str, str]]:
    """
    Parse ACB roster HTML and return list of players with:
      - acb_player_id (string)
      - name
      - position_raw (as ACB shows it, e.g. "Base", "Escolta", "Alero", "Ala-pívot", "Pívot")
    No external deps.
    """
    if not html:
        return []

    # 1) Narrow to the "JUGADORES" table body (keep it simple but robust)
    # We search for the table class "tabla_plantilla" and then capture tbody.
    m = re.search(
        r'<table[^>]*class="[^"]*tabla_plantilla[^"]*"[^>]*>.*?<tbody>(.*?)</tbody>\s*</table>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []

    tbody = m.group(1)

    # 2) Each row: grab player id+name and the position cell
    row_pattern = re.compile(
        r'<tr[^>]*>.*?'
        r'href="/jugador/ver/(\d+)-[^"]*"[^>]*>.*?'
        r'<span[^>]*class="nombre_corto"[^>]*>\s*(.*?)\s*</span>.*?'
        r'</a>\s*</td>\s*'
        r'<td[^>]*>\s*<span[^>]*>\s*(.*?)\s*</span>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    out: List[Dict[str, str]] = []
    seen = set()

    for pm in row_pattern.finditer(tbody):
        acb_player_id = pm.group(1).strip()
        name = unescape(pm.group(2)).strip()
        pos_raw = unescape(pm.group(3)).strip()

        name = re.sub(r"\s+", " ", name)
        pos_raw = re.sub(r"\s+", " ", pos_raw)

        key = (acb_player_id, name)
        if key in seen:
            continue
        seen.add(key)

        out.append(
            {
                "acb_player_id": acb_player_id,
                "name": name,
                "position_raw": pos_raw,
            }
        )

    return out

