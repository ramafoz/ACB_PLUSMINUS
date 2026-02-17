from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_wiki
from app.db.session import get_db

from app.schemas.wiki_players import WikiPlayersScrapeRequest

from app.scrapers.acb_players import fetch_team_roster_html, parse_roster_players, canonicalize_position
from app.models.teams import Team

from app.services.players_upsert import upsert_roster_players

router = APIRouter(prefix="/wiki/players", tags=["wiki"])

@router.post("/scrape")
def scrape_players_stub(
    payload: WikiPlayersScrapeRequest,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    # Pick first team from payload for now (single-team test)
    if not payload.team_ids:
        return {"ok": False, "detail": "team_ids is required for Step 5.1 (single-team fetch test)"}

    team_id = payload.team_ids[0].strip().upper()
    team = db.query(Team).filter(Team.season_id == payload.season_id, Team.team_id == team_id).first()
    if not team:
        return {"ok": False, "detail": f"Team not found for season_id={payload.season_id}, team_id={team_id}"}

    if not team.acb_club_id:
        return {"ok": False, "detail": f"Team {team_id} has no acb_club_id yet. Fill it first."}

    fetch_info = fetch_team_roster_html(team.acb_club_id, payload.season_id, include_html=True)

    if fetch_info["status_code"] != 200:
        return {"ok": False, "detail": "ACB request failed", "fetch": fetch_info}

    html = fetch_info.get("html", "")
    players = parse_roster_players(html)
    fetch_info.pop("html", None)

    preview = []
    for p in players:
        preview.append({
            "acb_player_id": p["acb_player_id"],
            "name": p["name"],
            "position_raw": p["position_raw"],
            "position": canonicalize_position(p["position_raw"]),
        })

    ins = upd = 0
    if not payload.dry_run:
        ins, upd = upsert_roster_players(db, payload.season_id, team.id, preview)
        db.commit()


    return {
        "ok": True,
        "step": "parse_players",
        "team_id": team_id,
        "acb_club_id": team.acb_club_id,
        "fetch": fetch_info,
        "parsed": {
            "players_count": len(preview),
            "players_sample": preview[:10],
        },
        "dry_run": payload.dry_run,
        "db": {"inserted": ins, "updated": upd},
    }
