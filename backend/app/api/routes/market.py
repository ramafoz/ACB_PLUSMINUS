from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.models.market import MarketPlayerPrice
from app.core.security import get_db
from app.core.game_config import SEASON_ID
from app.services.market_utils import compute_market_status, commit_round_if_needed

router = APIRouter(prefix="/api/v1", tags=["market"])


@router.get("/market")
def market(db: Session = Depends(get_db)):
    players = (
        db.query(MarketPlayerPrice)
        .order_by(MarketPlayerPrice.price_current.desc())
        .all()
    )

    return {
        "season_id": SEASON_ID,
        "players": [
            {
                "player_id": p.player_id,
                "name": p.name,
                "position": p.position,
                "team_name": p.team_name,
                "price": p.price_current,
            }
            for p in players
        ],
    }

@router.get("/market/status")
def market_status(db: Session = Depends(get_db)):
    commit_round_if_needed(db)
    ms = compute_market_status(db)
    return {
        "season_id": ms.season_id,
        "active_round": ms.active_round,
        "now": ms.now.isoformat(),
        "market_closes_at": ms.market_closes_at.isoformat() if ms.market_closes_at else None,
        "market_opens_at": ms.market_opens_at.isoformat() if ms.market_opens_at else None,
        "is_open": ms.is_open,
    }
