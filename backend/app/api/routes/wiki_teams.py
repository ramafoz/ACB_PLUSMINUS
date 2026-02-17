# app/api/routes/wikii_teams.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.game_config import ACB_TEMPORADA_ID
from app.core.security import get_db, require_wiki
from app.models.teams import Team
from app.schemas.teams import TeamCreate, TeamUpdate, TeamOut

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])


@router.post("/teams", response_model=TeamOut)
def create_team(payload: TeamCreate, user=Depends(require_wiki), db: Session = Depends(get_db), season_id: str = Query(default=ACB_TEMPORADA_ID),):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()
    team_id = payload.team_id.strip().upper()

    exists = db.query(Team).filter_by(season_id=ACB_TEMPORADA_ID, team_id=team_id).first()
    if exists:
        raise HTTPException(status_code=400, detail="team_id already exists for this season")

    t = Team(
        season_id=season_id,
        team_id=team_id,
        acb_club_id=(payload.acb_club_id.strip() if getattr(payload, "acb_club_id", None) else None),
        name=payload.name.strip(),
        short_name=(payload.short_name.strip() if payload.short_name else None),
        is_active=bool(payload.is_active) if payload.is_active is not None else True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/teams/{team_id}", response_model=TeamOut)
def update_team(team_id: str, payload: TeamUpdate, user=Depends(require_wiki), db: Session = Depends(get_db), season_id: str = Query(default=ACB_TEMPORADA_ID),):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()
    tid = team_id.strip().upper()
    t = db.query(Team).filter_by(season_id=ACB_TEMPORADA_ID, team_id=tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")

    if payload.name is not None:
        t.name = payload.name.strip()
    if payload.short_name is not None:
        t.short_name = payload.short_name.strip() if payload.short_name else None
    if getattr(payload, "acb_club_id", None) is not None:
        t.acb_club_id = payload.acb_club_id.strip() if payload.acb_club_id else None
    if payload.is_active is not None:
        t.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(t)
    return t


@router.delete("/teams/{team_id}", response_model=TeamOut)
def deactivate_team(
    team_id: str,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
    season_id: str = Query(default=ACB_TEMPORADA_ID),
):
    """
    Soft-delete: set is_active=False (keeps history and avoids FK issues).
    """
    season_id = (season_id or ACB_TEMPORADA_ID).strip()
    tid = team_id.strip().upper()

    t = db.query(Team).filter_by(season_id=season_id, team_id=tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")

    t.is_active = False
    db.commit()
    db.refresh(t)
    return t