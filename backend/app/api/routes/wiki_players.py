from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_wiki
from app.db.session import get_db

from app.schemas.wiki_players import WikiPlayersScrapeRequest

router = APIRouter(prefix="/wiki/players", tags=["wiki"])

@router.post("/scrape")
def scrape_players_stub(
    payload: WikiPlayersScrapeRequest,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    return {
        "ok": False,
        "detail": "Not implemented yet (Milestone 1 stub).",
        "requested_by_user_id": getattr(user, "id", None),
        "payload": payload.model_dump(),
    }