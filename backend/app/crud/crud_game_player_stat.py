from sqlalchemy.orm import Session
from app.models.game_player_stats import GamePlayerStat

def upsert_game_player_stats(db: Session, season_id: str, acb_game_id: str, rows: list[dict]) -> dict:
    created = 0
    updated = 0

    for r in rows:
        pid = r["acb_player_id"]
        row = (
            db.query(GamePlayerStat)
            .filter(
                GamePlayerStat.season_id == season_id,
                GamePlayerStat.acb_game_id == acb_game_id,
                GamePlayerStat.acb_player_id == pid,
            )
            .one_or_none()
        )

        if row is None:
            row = GamePlayerStat(
                season_id=season_id,
                acb_game_id=acb_game_id,
                acb_player_id=pid,
            )
            db.add(row)
            db.flush()
            created += 1
        else:
            updated += 1

        row.play_time = r.get("play_time")
        row.minutes_seconds = r.get("minutes_seconds")
        row.plus_minus = r.get("plus_minus")
        row.is_started = r.get("is_started")

    db.commit()
    return {"created": created, "updated": updated, "total": len(rows)}
