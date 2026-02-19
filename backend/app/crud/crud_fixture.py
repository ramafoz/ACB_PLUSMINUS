# app/crud/crud_fixture.py
from sqlalchemy.orm import Session

from app.models.fixtures import Fixture
from app.scrapers.acb_partidos import ParsedFixture  # IMPORTANT: use the real one

def upsert_fixtures(db: Session, season_id: str, parsed: list[ParsedFixture]) -> dict:
    created = 0
    updated = 0

    # Deduplicate within the batch (important with Next.js DOM repeating links/blocks)
    uniq: dict[tuple[int, str, str], ParsedFixture] = {}
    for fx in parsed:
        key = (fx.round_number, fx.home_team_id, fx.away_team_id)
        uniq[key] = fx
    parsed = list(uniq.values())

    for fx in parsed:
        row = (
            db.query(Fixture)
            .filter(
                Fixture.season_id == season_id,
                Fixture.round_number == fx.round_number,
                Fixture.home_team_id == fx.home_team_id,
                Fixture.away_team_id == fx.away_team_id,
            )
            .one_or_none()
        )

        if row is None:
            row = Fixture(
                season_id=season_id,
                round_number=fx.round_number,
                home_team_id=fx.home_team_id,
                away_team_id=fx.away_team_id,
            )
            db.add(row)
            db.flush()  # make INSERT visible to subsequent queries
            created += 1
        else:
            updated += 1

        row.kickoff_at = fx.kickoff_at
        row.is_finished = fx.is_finished
        row.home_score = fx.home_score
        row.away_score = fx.away_score

        # We recompute these later; still accept incoming values
        row.is_postponed = fx.is_postponed
        row.is_advanced = fx.is_advanced

        # IMPORTANT: do not overwrite a good value with None/empty
        if fx.acb_game_id:
            row.acb_game_id = fx.acb_game_id
        if fx.live_url:
            row.live_url = fx.live_url

    db.commit()
    return {"created": created, "updated": updated, "total": len(parsed)}
