from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_db
from app.core.game_config import ACB_TEMPORADA_ID
from app.models.fixtures import Fixture
from app.models.players import Player
from app.models.game_player_stats import GamePlayerStat
from app.schemas.game_player_stats import GamePlayerStatOut, PlayerPlusMinusAggOut

router = APIRouter(prefix="/api/v1/public", tags=["public"])


def _attach_player_team(db: Session, season_id: str, acb_player_id: str | None):
    if not acb_player_id:
        return None, None, None

    p = (
        db.query(Player)
        .filter(Player.season_id == season_id, Player.acb_player_id == acb_player_id)
        .first()
    )
    if not p:
        return None, None, None

    team_id = p.team.team_id if p.team else None
    team_name = p.team.name if p.team else None
    return p.name, team_id, team_name


@router.get("/stats/by_game", response_model=list[GamePlayerStatOut])
def public_stats_by_game(
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    acb_game_id: str = Query(...),
    db: Session = Depends(get_db),
):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()
    gid = acb_game_id.strip()

    rows = (
        db.query(GamePlayerStat)
        .filter(GamePlayerStat.season_id == season_id, GamePlayerStat.acb_game_id == gid)
        .order_by(GamePlayerStat.is_started.desc().nulls_last(), GamePlayerStat.minutes_seconds.desc().nulls_last())
        .all()
    )

    out: list[GamePlayerStatOut] = []
    for r in rows:
        player_name, team_id, team_name = _attach_player_team(db, season_id, r.acb_player_id)
        out.append(
            GamePlayerStatOut(
                season_id=r.season_id,
                acb_game_id=r.acb_game_id,
                acb_player_id=r.acb_player_id,
                player_name=player_name,
                team_id=team_id,
                team_name=team_name,
                play_time=r.play_time,
                minutes_seconds=r.minutes_seconds,
                plus_minus=r.plus_minus,
                is_started=r.is_started,
            )
        )
    return out


@router.get("/stats/by_fixture", response_model=list[GamePlayerStatOut])
def public_stats_by_fixture(
    fixture_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    f = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Fixture not found")
    if not f.acb_game_id:
        raise HTTPException(status_code=400, detail="Fixture has no acb_game_id")

    # Reuse the same logic as by_game
    return public_stats_by_game(season_id=f.season_id, acb_game_id=f.acb_game_id, db=db)


@router.get("/stats/by_player", response_model=list[GamePlayerStatOut])
def public_stats_by_player(
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    acb_player_id: str = Query(...),
    db: Session = Depends(get_db),
):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()
    pid = acb_player_id.strip()

    rows = (
        db.query(GamePlayerStat)
        .filter(GamePlayerStat.season_id == season_id, GamePlayerStat.acb_player_id == pid)
        .order_by(GamePlayerStat.acb_game_id.asc(), GamePlayerStat.updated_at.desc())
        .all()
    )

    player_name, team_id, team_name = _attach_player_team(db, season_id, pid)

    return [
        GamePlayerStatOut(
            season_id=r.season_id,
            acb_game_id=r.acb_game_id,
            acb_player_id=r.acb_player_id,
            player_name=player_name,
            team_id=team_id,
            team_name=team_name,
            play_time=r.play_time,
            minutes_seconds=r.minutes_seconds,
            plus_minus=r.plus_minus,
            is_started=r.is_started,
        )
        for r in rows
    ]


@router.get("/stats/leaderboard", response_model=list[PlayerPlusMinusAggOut])
def public_stats_leaderboard(
    season_id: str = Query(default=ACB_TEMPORADA_ID),
    round_number: int | None = Query(default=None, ge=1, le=60),
    min_minutes: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    season_id = (season_id or ACB_TEMPORADA_ID).strip()

    q = (
        db.query(
            GamePlayerStat.acb_player_id.label("acb_player_id"),
            func.count(GamePlayerStat.id).label("games"),
            func.coalesce(func.sum(GamePlayerStat.minutes_seconds), 0).label("minutes_seconds"),
            func.coalesce(func.sum(GamePlayerStat.plus_minus), 0).label("plus_minus"),
        )
        .filter(GamePlayerStat.season_id == season_id)
    )

    # Optional round filter by joining fixtures through acb_game_id
    if round_number is not None:
        q = q.join(
            Fixture,
            (Fixture.season_id == GamePlayerStat.season_id)
            & (Fixture.acb_game_id == GamePlayerStat.acb_game_id),
        ).filter(Fixture.round_number == round_number)

    q = q.group_by(GamePlayerStat.acb_player_id)

    # min minutes filter (post-aggregation)
    q = q.having(func.coalesce(func.sum(GamePlayerStat.minutes_seconds), 0) >= min_minutes)

    q = q.order_by(func.coalesce(func.sum(GamePlayerStat.plus_minus), 0).desc()).limit(limit)

    rows = q.all()

    out: list[PlayerPlusMinusAggOut] = []
    for r in rows:
        player_name, team_id, team_name = _attach_player_team(db, season_id, r.acb_player_id)
        out.append(
            PlayerPlusMinusAggOut(
                season_id=season_id,
                acb_player_id=r.acb_player_id,
                player_name=player_name,
                team_id=team_id,
                team_name=team_name,
                games=int(r.games or 0),
                minutes_seconds=int(r.minutes_seconds or 0),
                plus_minus=int(r.plus_minus or 0),
            )
        )
    return out