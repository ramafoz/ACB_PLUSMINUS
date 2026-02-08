from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.game_config import SEASON_ID
from app.models.season import SeasonState
from app.models.fixtures import Fixture

from app.models.roster import UserRosterBase, UserRosterDraft, UserSeasonState, UserCaptain
from app.models.user import User


@dataclass
class MarketStatus:
    season_id: str
    active_round: Optional[int]
    now: datetime
    market_closes_at: Optional[datetime]
    market_opens_at: Optional[datetime]
    is_open: bool


def _as_utc(dt: datetime) -> datetime:
    if dt is None:
        return None
    # Si viene naive, asumimos UTC (lo ideal es que no venga naive nunca)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)



def get_or_create_season_state(db: Session) -> SeasonState:
    st = db.query(SeasonState).filter_by(season_id=SEASON_ID).first()
    if not st:
        st = SeasonState(season_id=SEASON_ID, is_preseason=True)
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


def get_active_round(db: Session) -> Optional[int]:
    # Jornadas ordenadas
    rounds = (
        db.query(Fixture.round_number)
        .filter(Fixture.season_id == SEASON_ID)
        .distinct()
        .order_by(Fixture.round_number.asc())
        .all()
    )
    round_numbers = [r[0] for r in rounds]

    for rn in round_numbers:
        fixtures = (
            db.query(Fixture)
            .filter(Fixture.season_id == SEASON_ID)
            .filter(Fixture.round_number == rn)
            .filter(Fixture.is_advanced == False)  # noqa: E712
            .all()
        )

        relevant = [f for f in fixtures if (not f.is_postponed)]  # aquí advanced ya está filtrado
        # Si no hay relevantes, no sabemos si “cuenta”: la consideramos NO resuelta para que no salte
        if len(relevant) == 0:
            return rn

        round_resolved = all(f.is_finished for f in relevant)
        if not round_resolved:
            return rn

    # Si todas las jornadas están resueltas, devuelve la última (o None)
    return round_numbers[-1] if round_numbers else None


def refresh_market_window(db: Session) -> None:
    # por ahora solo recalcula status (no guarda nada)
    # más adelante: si cambia de cerrado->abierto, disparará commit o avanzará ronda
    compute_market_status(db)


def compute_market_status_for_round(db: Session, round_number: int, now: Optional[datetime] = None) -> MarketStatus:
    if now is None:
        now = datetime.now(timezone.utc)

    fixtures = (
        db.query(Fixture)
        .filter(Fixture.season_id == SEASON_ID)
        .filter(Fixture.round_number == round_number)
        .filter(Fixture.is_advanced == False)  # noqa: E712
        .all()
    )

    # Partidos "relevantes" para mercado: no avanzados.
    # - kickoff puede ser None (future/planned/postponed)
    # - is_postponed=True => ignorar para cierres/aperturas (pero cuenta como "resuelto" para abrir)
    # - is_finished=True + scores => jugado

    # 1) Cierre: 1h antes del primer kickoff de un partido válido (no postponed) con kickoff definido
    scheduled_with_time = [
        f for f in fixtures
        if (not f.is_postponed) and (f.kickoff_at is not None)
    ]
    first_kickoff = min((_as_utc(f.kickoff_at) for f in scheduled_with_time), default=None)
    market_closes_at = first_kickoff - timedelta(hours=1) if first_kickoff else None

    # 2) Apertura: 24h después del último partido "jugado" de la jornada,
    # siempre que NO queden partidos con kickoff futuro (scheduled) pendientes excepto postponed.
    # Interpretación:
    # - Si existe algún fixture con kickoff definido y no postponed y NOT finished => jornada NO resuelta => no abre
    relevant = [
        f for f in fixtures
        if (not f.is_advanced) and (not f.is_postponed)
    ]

    # Jornada resuelta si todos los relevantes están finished (si no hay relevantes, la tratamos como no resuelta)
    round_resolved = (len(relevant) > 0) and all(f.is_finished for f in relevant)

    if not round_resolved:
        market_opens_at = None
    else:
        finished_with_time = [f for f in relevant if f.is_finished and f.kickoff_at is not None]
        last_kickoff = max((_as_utc(f.kickoff_at) for f in finished_with_time), default=None)
        market_opens_at = (last_kickoff + timedelta(hours=24)) if last_kickoff else None


    # 3) is_open
    # Reglas:
    # - Si no hay market_closes_at -> está abierto (jornada futura sin fechas definidas)
    # - Si hay closes_at y now >= closes_at -> cerrado
    # - Si hay opens_at y now >= opens_at -> abierto (para la siguiente ventana)
    # En la práctica: una única ventana por jornada:
    # abierto (antes del close) -> cerrado (desde close hasta open) -> abierto (post-jornada)
    if market_closes_at is None:
        is_open = True
    else:
        if now < market_closes_at:
            is_open = True
        else:
            # cerrado hasta market_opens_at (si existe)
            is_open = (market_opens_at is not None) and (now >= market_opens_at)

    return MarketStatus(
        season_id=SEASON_ID,
        active_round=round_number,
        now=now,
        market_closes_at=market_closes_at,
        market_opens_at=market_opens_at,
        is_open=is_open,
    )


def compute_market_status(db: Session, now: Optional[datetime] = None) -> MarketStatus:
    # Asegura season_state exista (aunque aún no lo usemos)
    get_or_create_season_state(db)

    active_round = get_active_round(db)
    if active_round is None:
        # sin fixtures: mercado abierto por defecto
        if now is None:
            now = datetime.now()
        return MarketStatus(SEASON_ID, None, now, None, None, True)

    return compute_market_status_for_round(db, active_round, now=now)

def _user_can_edit_when_closed(
    db: Session,
    user_id: int,
    active_round: int,
) -> bool:
    # si ya está congelado para esta jornada -> no
    us = db.query(UserSeasonState).filter_by(user_id=user_id, season_id=SEASON_ID).first()
    if not us:
        return False
    if us.last_frozen_round == active_round:
        return False

    # si tiene huecos -> sí (solo add/undo)
    draft_count = db.query(UserRosterDraft).filter_by(user_id=user_id, season_id=SEASON_ID).count()
    return draft_count < 10

def freeze_user_if_ready(db: Session, user_id: int, active_round: int) -> None:
    us = db.query(UserSeasonState).filter_by(user_id=user_id, season_id=SEASON_ID).first()
    if not us:
        return

    if us.last_frozen_round == active_round:
        return

    draft_ids = [r.player_id for r in db.query(UserRosterDraft).filter_by(user_id=user_id, season_id=SEASON_ID).all()]
    if len(draft_ids) != 10:
        return

    # aquí podrías añadir validación de alineación (mínimos, max 2 por team, etc.)
    # por ahora solo “tiene 10”
    # y además capitán no puede ser null:
    cap = db.query(UserCaptain).filter_by(user_id=user_id, season_id=SEASON_ID).first()
    if not cap or not cap.captain_player_id:
        return

    # Freeze real:
    db.query(UserRosterBase).filter_by(user_id=user_id, season_id=SEASON_ID).delete()
    db.add_all([UserRosterBase(user_id=user_id, season_id=SEASON_ID, player_id=pid) for pid in draft_ids])

    us.budget_base = us.budget_current
    us.last_frozen_round = active_round

    db.commit()


def commit_round_if_needed(db: Session, now: Optional[datetime] = None) -> Optional[int]:
    st = get_or_create_season_state(db)
    active_round = get_active_round(db)
    if active_round is None:
        return None

    ms = compute_market_status_for_round(db, active_round, now=now)
    if ms.market_closes_at is None:
        return None

    # Si aún no ha llegado el cierre, no se comitea
    if ms.now < ms.market_closes_at:
        return None

    # Si ya se commiteó esta jornada, no repetir
    if st.last_committed_round == active_round:
        return None

    # COMMIT: draft -> base y budget_base = budget_current
    users = db.query(User).all()
    for u in users:
        # Asegura state usuario (tú ya tienes _get_or_create_state; si quieres reusar, lo movemos luego)
        us = db.query(UserSeasonState).filter_by(user_id=u.user_id, season_id=SEASON_ID).first()
        if not us:
            continue

        draft_ids = [r.player_id for r in db.query(UserRosterDraft).filter_by(user_id=u.user_id, season_id=SEASON_ID).all()]

        # Reemplazar base por draft (sí, aquí es correcto)
        db.query(UserRosterBase).filter_by(user_id=u.user_id, season_id=SEASON_ID).delete()
        db.add_all([UserRosterBase(user_id=u.user_id, season_id=SEASON_ID, player_id=pid) for pid in draft_ids])

        us.budget_base = us.budget_current

    # fin de pretemporada global al primer cierre real (asumimos jornada 1)
    if st.is_preseason:
        st.is_preseason = False

    st.last_committed_round = active_round
    st.updated_at = datetime.now(timezone.utc)
    db.commit()
    return active_round
