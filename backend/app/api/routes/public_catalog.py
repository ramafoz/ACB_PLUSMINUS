#app/api/routes/public_catalog.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.security import get_db
from app.core.game_config import ACB_TEMPORADA_ID
from app.models.teams import Team
from app.models.players import Player

router = APIRouter(prefix="/api/v1/public", tags=["public"])


class TeamPublicOut(BaseModel):
    season_id: str
    team_id: str
    acb_club_id: str | None
    name: str
    short_name: str | None
    is_active: bool

    class Config:
        from_attributes = True


class PlayerPublicOut(BaseModel):
    id: int
    season_id: str
    acb_player_id: str | None
    name: str
    position: str | None
    is_active: bool
    team_id: str | None
    team_name: str | None

    class Config:
        from_attributes = True

@router.get("/teams", response_model=list[TeamPublicOut])
def public_list_teams(
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    only_active: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()
    q = db.query(Team).filter(Team.season_id == season_id)
    if only_active:
        q = q.filter(Team.is_active == True)

    return q.order_by(Team.team_id.asc()).all()


@router.get("/players", response_model=list[PlayerPublicOut])
def public_list_players(
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    team_id: str | None = Query(default=None),     # Team.team_id (e.g. "BAR")
    only_active: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()

    q = db.query(Player).filter(Player.season_id == season_id)

    # If filtering by team_id, resolve to Team.id first (team_pk_id)
    team_pk_id = None
    team_name = None
    if team_id:
        tid = team_id.strip().upper()
        t = db.query(Team).filter(Team.season_id == season_id, Team.team_id == tid).first()
        if not t:
            return []
        team_pk_id = t.id
        team_name = t.name

    q = db.query(Player).filter(Player.season_id == season_id)
    if only_active:
        q = q.filter(Player.is_active == True)  # noqa: E712
    if team_pk_id is not None:
        q = q.filter(Player.team_pk_id == team_pk_id)

    rows = q.order_by(Player.name.asc(), Player.id.asc()).all()

    # attach team_id/team_name cheaply
    # (we can join later if you want, but this is simple & fast enough for ACB size)
    out: list[PlayerPublicOut] = []
    for p in rows:
        t = None
        if p.team_pk_id:
            t = db.query(Team).filter(Team.id == p.team_pk_id).first()
        out.append(
            PlayerPublicOut(
                id=p.id,
                season_id=p.season_id,
                acb_player_id=p.acb_player_id,
                name=p.name,
                position=p.position,
                is_active=p.is_active,
                team_id=(t.team_id if t else None),
                team_name=(t.name if t else team_name),
            )
        )

    return out