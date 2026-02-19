from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List
import time

from app.core.security import get_db, require_wiki
from app.core.game_config import SEASON_ID, ACB_COMPETICION_ID, ROUNDS_REGULAR_SEASON, ACB_JORNADA_ID_ROUND1
from app.crud.crud_fixture import upsert_fixtures
from app.models.fixtures import Fixture
from app.models.teams import Team
from app.schemas.fixtures import FixtureCreate, FixtureUpdate, FixtureOut
from app.scrapers.acb_partidos import scrape_partidos
from app.services.fixture_timing_flags import recompute_flags_roundcentric
from app.services.market_utils import compute_market_status

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])

class ReseedFixturesIn(BaseModel):
    season_id: str = Field(default=SEASON_ID)
    start_round_number: int = Field(default=1, ge=1, le=60)
    rounds: int = Field(ge=1, le=60)

    # optional:
    replace_rounds: bool = Field(default=False)
    tol_minutes: int = Field(default=0, ge=0, le=180)
    include_flagged: bool = Field(default=True)


class ReseedFixturesOut(BaseModel):
    season_id: str
    rounds_requested: int
    upsert_created: int
    upsert_updated: int
    parsed_total: int
    flags_updated_rows: int
    advanced: int
    postponed: int
    flagged: list[dict] = []
    warnings: list[str] = []
    rounds_incomplete: list[dict] = []

@router.post("/fixtures/reseed_from_acb", response_model=ReseedFixturesOut)
def reseed_fixtures_from_acb(
    payload: ReseedFixturesIn,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    # 1) scrape + upsert
    total_created = 0
    total_updated = 0
    total_parsed = 0

    # hard replace the rounds we are about to reseed
    if payload.replace_rounds:
        for i in range(payload.rounds):
            rn = payload.start_round_number + i
            db.query(Fixture).filter(
                Fixture.season_id == payload.season_id,
                Fixture.round_number == rn,
            ).delete(synchronize_session=False)
        db.commit()
    
    end_round = payload.start_round_number + payload.rounds - 1
    if end_round > ROUNDS_REGULAR_SEASON:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid range: start_round_number={payload.start_round_number}, rounds={payload.rounds} exceeds ROUNDS_REGULAR_SEASON={ROUNDS_REGULAR_SEASON}",
        )

    warnings: list[str] = []
    rounds_incomplete: list[dict] = []

    t0 = time.time()
    print(
        f"[reseed] season={payload.season_id} rounds={payload.rounds} "
        f"range={payload.start_round_number}-{end_round} tol={payload.tol_minutes}min",
        flush=True,
    )

    for i in range(payload.rounds):
        round_number = payload.start_round_number + i
        jornada_id = ACB_JORNADA_ID_ROUND1 + (round_number -1)

        t_round = time.time()
        print(f"[reseed] round {round_number:02d}/{end_round:02d} jornada_id={jornada_id} ...", flush=True)

        parsed = scrape_partidos(
            season_id=payload.season_id,
            competicion=ACB_COMPETICION_ID,
            jornada_id=jornada_id,
            round_number=round_number
        )

        if not parsed:
            msg = f"Round {round_number} jornada_id={jornada_id}: parsed=0 (ACB empty/partial)"
            warnings.append(msg)
            rounds_incomplete.append({"round_number": round_number, "jornada_id": jornada_id, "parsed": 0})
            print(f"[reseed][WARN] {msg}", flush=True)
            continue

        if len(parsed) != 9:
            msg = f"Round {round_number} jornada_id={jornada_id}: parsed={len(parsed)} (expected 9)"
            warnings.append(msg)
            rounds_incomplete.append({"round_number": round_number, "jornada_id": jornada_id, "parsed": len(parsed)})
            print(f"[reseed][WARN] {msg}", flush=True)

        # map to what upsert expects (your existing pattern)
        mapped = []
        for fx in parsed:
            mapped.append(
                type("Tmp", (), {
                    "round_number": round_number,
                    "home_team_id": fx.home_team_id,
                    "away_team_id": fx.away_team_id,
                    "kickoff_at": fx.kickoff_at,
                    "is_finished": fx.is_finished,
                    "home_score": fx.home_score,
                    "away_score": fx.away_score,
                    "is_postponed": fx.is_postponed,
                    "is_advanced": fx.is_advanced,
                    "acb_game_id": getattr(fx, "acb_game_id", None),
                    "live_url": getattr(fx, "live_url", None),
                })()
            )

        res = upsert_fixtures(db, season_id=payload.season_id, parsed=mapped)
        total_created += int(res.get("created", 0))
        total_updated += int(res.get("updated", 0))
        total_parsed += int(res.get("total", 0))

        dt_round = time.time() - t_round
        print(
            f"[reseed] round {round_number:02d} done: parsed={len(parsed)} "
            f"created={res.get('created', 0)} updated={res.get('updated', 0)} "
            f"elapsed={dt_round:.1f}s",
            flush=True,
        )

    # 2) recompute flags (round-centric)
    print("[reseed] recompute flags ...", flush=True)
    t_flags = time.time()
    flags_res = recompute_flags_roundcentric(
        db,
        season_id=payload.season_id,
        tol_minutes=payload.tol_minutes,
    )
    print(
        f"[reseed] flags done: updated={flags_res.get('updated', 0)} "
        f"advanced={flags_res.get('advanced', 0)} postponed={flags_res.get('postponed', 0)} "
        f"elapsed={time.time() - t_flags:.1f}s",
        flush=True,
    )

    # 3) optionally return flagged list
    flagged_list = []
    if payload.include_flagged:
        flagged_rows = (
            db.query(Fixture)
            .filter(
                Fixture.season_id == payload.season_id,
                ((Fixture.is_postponed == True) | (Fixture.is_advanced == True)),
            )
            .order_by(Fixture.round_number.asc(), Fixture.kickoff_at.asc().nulls_last(), Fixture.id.asc())
            .all()
        )
        for f in flagged_rows:
            flagged_list.append({
                "id": f.id,
                "round_number": f.round_number,
                "home_team_id": f.home_team_id,
                "away_team_id": f.away_team_id,
                "kickoff_at": f.kickoff_at,
                "is_advanced": f.is_advanced,
                "is_postponed": f.is_postponed,
                "is_finished": f.is_finished,
                "home_score": f.home_score,
                "away_score": f.away_score,
            })

    compute_market_status(db)

    print(
        f"[reseed] DONE season={payload.season_id} total_parsed={total_parsed} "
        f"created={total_created} updated={total_updated} total_elapsed={time.time()-t0:.1f}s",
        flush=True,
    )

    return ReseedFixturesOut(
        season_id=payload.season_id,
        rounds_requested=payload.rounds,
        upsert_created=total_created,
        upsert_updated=total_updated,
        parsed_total=total_parsed,
        flags_updated_rows=int(flags_res.get("updated", 0)),
        advanced=int(flags_res.get("advanced", 0)),
        postponed=int(flags_res.get("postponed", 0)),
        flagged=flagged_list,
        warnings=warnings,
        rounds_incomplete=rounds_incomplete,
    )

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
    season_id = payload.season_id  # <-- make sure FixtureCreate includes it
    # or: season_id = SEASON_ID if you don't want it in payload

    # validar equipos
    for tid in (payload.home_team_id, payload.away_team_id):
        team = db.query(Team).filter_by(
            season_id=season_id, team_id=tid, is_active=True
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
        season_id=season_id,
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
    f = db.query(Fixture).filter_by(id=fixture_id, season_id=payload.season_id).first()
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

class RecomputeFlagsIn(BaseModel):
    season_id: str = Field(default=SEASON_ID)
    tol_minutes: int = Field(default=0, ge=0, le=180)
    include_flagged: bool = True


@router.post("/fixtures/recompute_flags", response_model=ReseedFixturesOut)
def recompute_flags_only(
    payload: RecomputeFlagsIn,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    flags_res = recompute_flags_roundcentric(
        db,
        season_id=payload.season_id,
        tol_minutes=payload.tol_minutes,
    )

    compute_market_status(db)

    flagged_list = []
    if payload.include_flagged:
        flagged_rows = (
            db.query(Fixture)
            .filter(
                Fixture.season_id == payload.season_id,
                ((Fixture.is_postponed == True) | (Fixture.is_advanced == True)),
            )
            .order_by(Fixture.round_number.asc(), Fixture.kickoff_at.asc().nulls_last(), Fixture.id.asc())
            .all()
        )
        flagged_list = [{
            "id": f.id,
            "round_number": f.round_number,
            "home_team_id": f.home_team_id,
            "away_team_id": f.away_team_id,
            "kickoff_at": f.kickoff_at,
            "is_advanced": f.is_advanced,
            "is_postponed": f.is_postponed,
            "is_finished": f.is_finished,
            "home_score": f.home_score,
            "away_score": f.away_score,
        } for f in flagged_rows]

    # reuse your output model, filling the parts that don't apply
    return ReseedFixturesOut(
        season_id=payload.season_id,
        rounds_requested=0,
        upsert_created=0,
        upsert_updated=0,
        parsed_total=0,
        flags_updated_rows=int(flags_res.get("updated", 0)),
        advanced=int(flags_res.get("advanced", 0)),
        postponed=int(flags_res.get("postponed", 0)),
        flagged=flagged_list,
    )


@router.get("/fixtures/summary")
def fixtures_summary(
    season_id: str = SEASON_ID,
    user=Depends(require_wiki),
    db: Session = Depends(get_db),
):
    total = db.query(func.count(Fixture.id)).filter(Fixture.season_id == season_id).scalar() or 0

    per_round = (
        db.query(Fixture.round_number, func.count(Fixture.id))
        .filter(Fixture.season_id == season_id)
        .group_by(Fixture.round_number)
        .order_by(Fixture.round_number.asc())
        .all()
    )

    advanced = db.query(func.count(Fixture.id)).filter(Fixture.season_id == season_id, Fixture.is_advanced == True).scalar() or 0
    postponed = db.query(func.count(Fixture.id)).filter(Fixture.season_id == season_id, Fixture.is_postponed == True).scalar() or 0
    null_kickoff = db.query(func.count(Fixture.id)).filter(Fixture.season_id == season_id, Fixture.kickoff_at == None).scalar() or 0

    bad_rounds = [{"round_number": r, "count": c} for (r, c) in per_round if c != 9]

    return {
        "season_id": season_id,
        "total": int(total),
        "advanced": int(advanced),
        "postponed": int(postponed),
        "null_kickoff": int(null_kickoff),
        "rounds": [{"round_number": int(r), "count": int(c)} for (r, c) in per_round],
        "rounds_with_count_not_9": bad_rounds,
    }
