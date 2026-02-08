from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.game_config import SEASON_ID
from app.core.security import get_db
from app.models.teams import Team
from app.schemas.teams import TeamOut

router = APIRouter(prefix="/api/v1", tags=["teams"])


@router.get("/teams", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db), active_only: bool = True):
    q = db.query(Team).filter(Team.season_id == SEASON_ID)
    if active_only:
        q = q.filter(Team.is_active == True)  # noqa: E712
    return q.order_by(Team.name.asc()).all()
