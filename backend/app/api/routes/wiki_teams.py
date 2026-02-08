from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.game_config import SEASON_ID
from app.core.security import get_db, require_wiki
from app.models.teams import Team
from app.schemas.teams import TeamCreate, TeamUpdate, TeamOut

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])


@router.post("/teams", response_model=TeamOut)
def create_team(payload: TeamCreate, user=Depends(require_wiki), db: Session = Depends(get_db)):
    team_id = payload.team_id.strip().upper()

    exists = db.query(Team).filter_by(season_id=SEASON_ID, team_id=team_id).first()
    if exists:
        raise HTTPException(status_code=400, detail="team_id already exists for this season")

    t = Team(
        season_id=SEASON_ID,
        team_id=team_id,
        name=payload.name.strip(),
        short_name=(payload.short_name.strip() if payload.short_name else None),
        is_active=bool(payload.is_active),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/teams/{team_id}", response_model=TeamOut)
def update_team(team_id: str, payload: TeamUpdate, user=Depends(require_wiki), db: Session = Depends(get_db)):
    tid = team_id.strip().upper()
    t = db.query(Team).filter_by(season_id=SEASON_ID, team_id=tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")

    if payload.name is not None:
        t.name = payload.name.strip()
    if payload.short_name is not None:
        t.short_name = payload.short_name.strip() if payload.short_name else None
    if payload.is_active is not None:
        t.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(t)
    return t
