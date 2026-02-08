from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.core.security import get_db
from app.core.game_config import SEASON_ID
from app.models.fixtures import Fixture
from app.schemas.fixtures import FixtureOut

router = APIRouter(prefix="/api/v1", tags=["fixtures"])


@router.get("/fixtures", response_model=list[FixtureOut])
def list_public_fixtures(
    round_number: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Fixture).filter_by(season_id=SEASON_ID)

    if round_number is not None:
        q = q.filter(Fixture.round_number == round_number)

    # Ojo: al público le interesa ver orden por jornada y fecha
    return (
        q.order_by(
            Fixture.round_number.asc(),
            Fixture.kickoff_at.asc().nulls_last(),
            Fixture.id.asc(),
        )
        .all()
    )
