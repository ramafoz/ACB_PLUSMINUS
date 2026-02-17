from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.security import get_db, require_wiki
from app.core.game_config import SEASON_ID
from app.models.fixtures import Fixture
from app.models.teams import Team
from app.schemas.fixtures import FixtureCreate, FixtureUpdate, FixtureOut
from app.services.market_utils import compute_market_status

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])

def _validate_fixture_state(is_postponed: bool, is_advanced: bool, is_finished: bool,
                           home_score: int | None, away_score: int | None):
    # Estados incompatibles
    if is_postponed and (is_advanced):
        raise HTTPException(status_code=400, detail="Invalid state: postponed cannot be advanced")

    if is_advanced and (is_postponed):
        raise HTTPException(status_code=400, detail="Invalid state: advanced cannot be postponed")

    # Finished requiere scores
    if is_finished and (home_score is None or away_score is None):
        raise HTTPException(status_code=400, detail="Finished fixture requires home_score and away_score")

    # (Opcional pero recomendable) si NO está finished, no permitas scores
    if not is_finished and (home_score is not None or away_score is not None):
        raise HTTPException(status_code=400, detail="Scores can only be set when fixture is finished")

    # (Opcional) si postponed, scores deben ser None
    if is_postponed and (home_score is not None or away_score is not None):
        raise HTTPException(status_code=400, detail="Postponed fixture cannot have scores")



@router.post("/fixtures", response_model=FixtureOut)
def create_fixture(
    payload: FixtureCreate,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    # validar equipos
    for tid in (payload.home_team_id, payload.away_team_id):
        team = db.query(Team).filter_by(
            season_id=SEASON_ID, team_id=tid, is_active=True
        ).first()
        if not team:
            raise HTTPException(status_code=400, detail=f"Invalid or inactive team: {tid}")

    if payload.home_team_id == payload.away_team_id:
        raise HTTPException(status_code=400, detail="Home and away team cannot be the same")
    
    _validate_fixture_state(
        is_postponed=payload.is_postponed,
        is_advanced=payload.is_advanced,
        is_finished=False,
        home_score=None,
        away_score=None,
    )

    f = Fixture(
        season_id=SEASON_ID,
        round_number=payload.round_number,
        home_team_id=payload.home_team_id,
        away_team_id=payload.away_team_id,
        kickoff_at=payload.kickoff_at,
        is_postponed=payload.is_postponed,
        is_advanced=payload.is_advanced,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f

@router.get("/fixtures", response_model=list[FixtureOut])
def list_fixtures(
    season_id: str = SEASON_ID,
    round_number: Optional[int] = None,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    q = db.query(Fixture).filter(Fixture.season_id == season_id)
    if round_number is not None:
        q = q.filter(Fixture.round_number == round_number)

    return q.order_by(Fixture.round_number.asc(), Fixture.kickoff_at.asc().nulls_last(), Fixture.id.asc()).all()

@router.patch("/fixtures/{fixture_id}", response_model=FixtureOut)
def update_fixture(
    fixture_id: int,
    payload: FixtureUpdate,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    f = db.query(Fixture).filter_by(id=fixture_id, season_id=SEASON_ID).first()
    if not f:
        raise HTTPException(status_code=404, detail="Fixture not found")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(f, field, value)

    _validate_fixture_state(
        is_postponed=f.is_postponed,
        is_advanced=f.is_advanced,
        is_finished=f.is_finished,
        home_score=f.home_score,
        away_score=f.away_score,
    )

    db.commit()
    db.refresh(f)
    # Disparador: al actualizar un fixture, recalculamos mercado (sirve para logs/commit futuro)
    compute_market_status(db)
    return f

