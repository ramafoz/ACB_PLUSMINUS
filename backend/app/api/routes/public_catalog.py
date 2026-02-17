from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.security import get_db
from app.core.game_config import SEASON_ID
from app.models.teams import Team
from app.models.players import Player

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/teams")
def public_list_teams(
    season_id: str = SEASON_ID,
    only_active: bool = True,
    db: Session = Depends(get_db),
):
    q = db.query(Team).filter(Team.season_id == season_id)
    if only_active:
        q = q.filter(Team.is_active == True)

    rows = q.order_by(Team.name.asc()).all()

    return [
        {
            "team_id": t.team_id,           # e.g. "BAR", "RMB"
            "acb_club_id": t.acb_club_id,   # e.g. "14"
            "name": t.name,                # e.g. "FC Barcelona"
            "short_name": t.short_name,    # e.g. "Barça"
            "is_active": t.is_active,
        }
        for t in rows
    ]


@router.get("/players")
def public_list_players(
    season_id: str = SEASON_ID,
    team_id: Optional[str] = None,                 # Team.team_id (e.g. "BAR")
    team_pk_id: Optional[int] = None,              # Team.id (PK)
    only_active: bool = True,
    db: Session = Depends(get_db),
):
    q = db.query(Player).filter(Player.season_id == season_id)

    if only_active:
        q = q.filter(Player.is_active == True)

    # Allow filtering either by team_pk_id OR by team_id (human-friendly)
    if team_pk_id is not None:
        q = q.filter(Player.team_pk_id == team_pk_id)
    elif team_id is not None:
        # join via relationship (Player.team is lazy="joined", but we still join for filtering)
        q = q.join(Player.team).filter(Team.team_id == team_id, Team.season_id == season_id)

    rows = q.order_by(Player.name.asc()).all()

    return [
        {
            "id": p.id,
            "acb_player_id": p.acb_player_id,
            "name": p.name,
            "position": p.position,
            "is_active": p.is_active,
            "team_pk_id": p.team_pk_id,
            # include team fields to avoid extra call on frontend
            "team": (
                {
                    "team_id": p.team.team_id,
                    "acb_club_id": p.team.acb_club_id,
                    "name": p.team.name,
                    "short_name": p.team.short_name,
                    "is_active": p.team.is_active,
                }
                if p.team is not None
                else None
            ),
        }
        for p in rows
    ]

@router.get("/teams/{team_id}/players")
def public_list_team_players(
    team_id: str,
    season_id: str = SEASON_ID,
    only_active: bool = True,
    db: Session = Depends(get_db),
):
    team = (
        db.query(Team)
        .filter(Team.season_id == season_id, Team.team_id == team_id)
        .first()
    )
    if not team:
        return []

    q = db.query(Player).filter(Player.season_id == season_id, Player.team_pk_id == team.id)
    if only_active:
        q = q.filter(Player.is_active == True)

    rows = q.order_by(Player.name.asc()).all()

    return [
        {
            "id": p.id,
            "acb_player_id": p.acb_player_id,
            "name": p.name,
            "position": p.position,
            "is_active": p.is_active,
        }
        for p in rows
    ]
