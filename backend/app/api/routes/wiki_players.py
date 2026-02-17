from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.security import require_wiki
from app.db.session import get_db

from app.core.game_config import ACB_TEMPORADA_ID

from app.schemas.wiki_players import WikiPlayersScrapeRequest

from app.scrapers.acb_players import fetch_team_roster_html, parse_roster_players, canonicalize_position
from app.models.teams import Team
from app.models.players import Player

from app.services.players_upsert import upsert_roster_players
from app.services.wiki_resync_players import resync_players_from_acb
from app.schemas.wiki_players_crud import WikiPlayerCreate, WikiPlayerUpdate


router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])

@router.post("/scrape_players")
def scrape_players_stub(
    payload: WikiPlayersScrapeRequest,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    # If team_ids is omitted/empty => scrape ALL active teams for that season.
    requested_team_ids = [t.strip().upper() for t in (payload.team_ids or []) if t and t.strip()]

    q = db.query(Team).filter(
        Team.season_id == payload.temporada_id,
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

        fetch_info = fetch_team_roster_html(
            acb_club_id=team.acb_club_id, 
            season_id=payload.temporada_id,
            include_html=True
        )
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
            ins, upd = upsert_roster_players(db, payload.temporada_id, team.id, preview)
            total_inserted += ins
            total_updated += upd

            # Deactivate players that were previously active for this team+season but are not in the scraped roster now
            seen_ids = {p.get("acb_player_id") for p in preview if p.get("acb_player_id")}
            if seen_ids:
                deactivated = (
                    db.query(Player)
                    .filter(
                        Player.season_id == payload.temporada_id,
                        Player.team_pk_id == team.id,
                        Player.acb_player_id.isnot(None),
                        Player.is_active == True,  # noqa: E712
                        ~Player.acb_player_id.in_(seen_ids),
                    )
                    .update({Player.is_active: False}, synchronize_session=False)
                )
                total_deactivated += deactivated

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
        "season_id": payload.temporada_id,
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


class ResyncPlayersIn(BaseModel):
    season_id: str = Field(default=ACB_TEMPORADA_ID)
    only_active_teams: bool = True

class ResyncPlayersOut(BaseModel):
    season_id: str
    teams_ok: int
    teams_failed: int
    created: int
    updated: int
    deactivated: int

@router.post("/resync_players_from_acb", response_model=ResyncPlayersOut)
def wiki_resync_players_from_acb(
    payload: ResyncPlayersIn,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    res = resync_players_from_acb(db, season_id=payload.season_id, only_active_teams=payload.only_active_teams)
    return ResyncPlayersOut(season_id=payload.season_id, **res)


@router.post("/players")
def wiki_create_player(payload: WikiPlayerCreate, user=Depends(require_wiki), db: Session = Depends(get_db)):
    sid = (payload.season_id or ACB_TEMPORADA_ID).strip()
    team_code = payload.team_id.strip().upper()

    team = db.query(Team).filter(Team.season_id == sid, Team.team_id == team_code).first()
    if not team:
        raise HTTPException(status_code=400, detail=f"Unknown team_id for season: {team_code}")

    acb_pid = (payload.acb_player_id.strip() if payload.acb_player_id else None)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    # prevent duplicates if acb_player_id exists
    if acb_pid:
        exists = db.query(Player).filter(Player.season_id == sid, Player.acb_player_id == acb_pid).first()
        if exists:
            raise HTTPException(status_code=400, detail="acb_player_id already exists for this season")

    p = Player(
        season_id=sid,
        acb_player_id=acb_pid,
        name=name,
        position=(payload.position.strip() if payload.position else None),
        team_pk_id=team.id,
        is_active=bool(payload.is_active),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"ok": True, "id": p.id}


@router.patch("/players/{player_id}")
def wiki_update_player(
    player_id: int,
    payload: WikiPlayerUpdate,
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    sid = (season_id or ACB_TEMPORADA_ID).strip()
    p = db.query(Player).filter(Player.id == player_id, Player.season_id == sid).first()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")

    if payload.team_id is not None:
        team_code = payload.team_id.strip().upper()
        team = db.query(Team).filter(Team.season_id == sid, Team.team_id == team_code).first()
        if not team:
            raise HTTPException(status_code=400, detail=f"Unknown team_id for season: {team_code}")
        p.team_pk_id = team.id

    if payload.name is not None:
        nm = payload.name.strip()
        if not nm:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        p.name = nm

    if payload.position is not None:
        p.position = payload.position.strip() if payload.position else None

    if payload.acb_player_id is not None:
        new_acb = payload.acb_player_id.strip() if payload.acb_player_id else None
        if new_acb:
            exists = db.query(Player).filter(
                Player.season_id == sid,
                Player.acb_player_id == new_acb,
                Player.id != p.id,
            ).first()
            if exists:
                raise HTTPException(status_code=400, detail="acb_player_id already exists for this season")
        p.acb_player_id = new_acb

    if payload.is_active is not None:
        p.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(p)
    return {"ok": True, "id": p.id}


@router.delete("/players/{player_id}")
def wiki_deactivate_player(
    player_id: int,
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    sid = (season_id or ACB_TEMPORADA_ID).strip()
    p = db.query(Player).filter(Player.id == player_id, Player.season_id == sid).first()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")

    p.is_active = False
    db.commit()
    return {"ok": True}