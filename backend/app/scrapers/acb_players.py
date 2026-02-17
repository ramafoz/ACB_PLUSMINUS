from typing import Optional, Dict, Any
from app.scrapers.http import make_client


def fetch_team_roster_html(acb_club_id: str) -> Dict[str, Any]:
    """
    Fetch raw HTML for an ACB team roster page.
    Manual-only; called by wiki/admin endpoint.
    """
    url = f"https://www.acb.com/club/plantilla/id/{acb_club_id}"
    with make_client() as client:
        resp = client.get(url)
        return {
            "requested_url": url,
            "final_url": str(resp.url),
            "status_code": resp.status_code,
            "html_len": len(resp.text or ""),
        }