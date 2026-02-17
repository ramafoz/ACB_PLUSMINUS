from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_wiki
from app.db.session import get_db

router = APIRouter(prefix="/wiki/players", tags=["wiki"])

@router.post("/scrape")
def scrape_players_stub(
    db: Session = Depends(get_db),
    user=Depends(require_wiki),
):
    # Stub: later this will scrape ACB roster pages and upsert players.
    return {
        "ok": False,
        "detail": "Not implemented yet (Milestone 1 stub).",
        "requested_by_user_id": getattr(user, "id", None),
    }
