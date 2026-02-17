from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_wiki
from app.db.session import get_db

from app.schemas.wiki_players import WikiPlayersScrapeRequest

from app.scrapers.acb_players import fetch_team_roster_html, parse_roster_players, canonicalize_position
from app.models.teams import Team
from app.models.players import Player

from app.services.players_upsert import upsert_roster_players

router = APIRouter(prefix="/wiki/players", tags=["wiki"])

@router.post("/scrape")
def scrape_players_stub(
    payload: WikiPlayersScrapeRequest,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    # If team_ids is omitted/empty => scrape ALL active teams for that season.
    requested_team_ids = [t.strip().upper() for t in (payload.team_ids or []) if t and t.strip()]

    q = db.query(Team).filter(
        Team.season_id == payload.season_id,
        Team.is_active == True,  # noqa: E712
    )

    if requested_team_ids:
        q = q.filter(Team.team_id.in_(requested_team_ids))

    teams = q.all()
    if not teams:
        return {"ok": False, "detail": "No matching teams found for this season/team_ids"}

    results = []
    total_inserted = 0
    total_updated = 0
    total_deactivated = 0
    total_players = 0

    for team in teams:
        if not team.acb_club_id:
            results.append({"team_id": team.team_id, "ok": False, "detail": "missing acb_club_id"})
            continue

        fetch_info = fetch_team_roster_html(team.acb_club_id, payload.season_id, include_html=True)
        if fetch_info.get("status_code") != 200:
            results.append({"team_id": team.team_id, "ok": False, "detail": "ACB request failed", "fetch": fetch_info})
            continue

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

        ins = upd = deactivated = 0

        if not payload.dry_run:
            ins, upd = upsert_roster_players(db, payload.season_id, team.id, preview)
            total_inserted += ins
            total_updated += upd
            total_deactivated += deactivated

            # Deactivate players that were previously active for this team+season but are not in the scraped roster now
            seen_ids = {p.get("acb_player_id") for p in preview if p.get("acb_player_id")}
            if seen_ids:
                deactivated = (
                    db.query(Player)
                    .filter(
                        Player.season_id == payload.season_id,
                        Player.team_pk_id == team.id,
                        Player.acb_player_id.isnot(None),
                        Player.is_active == True,  # noqa: E712
                        ~Player.acb_player_id.in_(seen_ids),
                    )
                    .update({Player.is_active: False}, synchronize_session=False)
                )

        total_players += len(preview)

        results.append({
            "team_id": team.team_id,
            "acb_club_id": team.acb_club_id,
            "players_count": len(preview),
            "players_sample": preview[:5],  # keep response small
            "db": {"inserted": ins, "updated": upd, "deactivated": deactivated},
            "fetch": fetch_info,
            "ok": True,
        })

    if not payload.dry_run:
        db.commit()

    return {
        "ok": True,
        "step": "7.1_multi_team",
        "season_id": payload.season_id,
        "dry_run": payload.dry_run,
        "requested_team_ids": requested_team_ids,
        "totals": {
            "teams_requested": len(teams),
            "teams_processed": sum(1 for r in results if r.get("ok")),
            "players_parsed": total_players,
            "inserted": total_inserted,
            "updated": total_updated,
            "deactivated": total_deactivated,
        },
        "results": results,
    }
