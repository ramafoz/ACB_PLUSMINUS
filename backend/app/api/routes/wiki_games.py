from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_db, require_wiki
from app.models.fixtures import Fixture
from app.scrapers.acb_live_stats import fetch_live_stats_html, parse_minutes_plusminus
from app.crud.crud_game_player_stat import upsert_game_player_stats

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])

class ReseedPlayerStatsIn(BaseModel):
    season_id: str
    start_round_number: int = Field(default=1, ge=1, le=60)
    rounds: int = Field(ge=1, le=60)
    replace: bool = False  # delete existing rows for those games first

class ReseedPlayerStatsOut(BaseModel):
    season_id: str
    rounds_requested: int
    games_found: int
    games_processed: int
    rows_created: int
    rows_updated: int
    warnings: list[str] = []

@router.post("/games/reseed_playerstats_from_final", response_model=ReseedPlayerStatsOut)
def reseed_playerstats_from_final(
    payload: ReseedPlayerStatsIn,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    end_round = payload.start_round_number + payload.rounds - 1

    fixtures = (
        db.query(Fixture)
        .filter(
            Fixture.season_id == payload.season_id,
            Fixture.round_number >= payload.start_round_number,
            Fixture.round_number <= end_round,
        )
        .order_by(Fixture.round_number.asc(), Fixture.id.asc())
        .all()
    )

    warnings: list[str] = []
    games_processed = 0
    rows_created = 0
    rows_updated = 0

    with_game = [f for f in fixtures if f.acb_game_id]
    games_found = len(with_game)

    if games_found == 0:
        warnings.append("No fixtures with acb_game_id. Did you reseed fixtures after adding acb_game_id extraction?")
        return ReseedPlayerStatsOut(
            season_id=payload.season_id,
            rounds_requested=payload.rounds,
            games_found=0,
            games_processed=0,
            rows_created=0,
            rows_updated=0,
            warnings=warnings,
        )

    if payload.replace:
        from app.models.game_player_stats import GamePlayerStat
        game_ids = [f.acb_game_id for f in with_game if f.acb_game_id]
        db.query(GamePlayerStat).filter(
            GamePlayerStat.season_id == payload.season_id,
            GamePlayerStat.acb_game_id.in_(game_ids),
        ).delete(synchronize_session=False)
        db.commit()

    for f in with_game:
        gid = f.acb_game_id
        try:
            html = fetch_live_stats_html(gid)  # now fetches FINAL official stats via acb.com
            rows = parse_minutes_plusminus(html)
            res = upsert_game_player_stats(db, payload.season_id, gid, rows)
            rows_created += int(res.get("created", 0))
            rows_updated += int(res.get("updated", 0))
            games_processed += 1
        except Exception as e:
            warnings.append(f"game_id={gid} fixture_id={f.id}: {type(e).__name__}: {e}")

    return ReseedPlayerStatsOut(
        season_id=payload.season_id,
        rounds_requested=payload.rounds,
        games_found=games_found,
        games_processed=games_processed,
        rows_created=rows_created,
        rows_updated=rows_updated,
        warnings=warnings,
    )