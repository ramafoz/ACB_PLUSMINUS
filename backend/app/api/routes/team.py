from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_current_user
from app.core.game_config import (
    SEASON_ID, INITIAL_BUDGET, MAX_PLAYERS, MAX_PER_REAL_TEAM, MAX_TOTAL_CHANGES, MIN_BY_POSITION, ALL_POSITIONS
)
from app.db.session import get_db
from app.models.user import User
from app.models.market import MarketPlayerPrice
from app.models.roster import UserSeasonState, UserRosterBase, UserRosterDraft, UserCaptain, UserDraftAction
from app.schemas.team import CaptainRequest, InitTeamRequest, PlayerIdRequest
from app.services.market_utils import compute_market_status, commit_round_if_needed, get_or_create_season_state



router = APIRouter(prefix="/api/v1/me", tags=["team"])

def _count_positions_for_ids(db: Session, player_ids: set[str]) -> dict[str, int]:
    counts = {pos: 0 for pos in ALL_POSITIONS}
    if not player_ids:
        return counts

    rows = (
        db.query(MarketPlayerPrice.position)
        .filter(MarketPlayerPrice.season_id == SEASON_ID)
        .filter(MarketPlayerPrice.player_id.in_(list(player_ids)))
        .all()
    )
    # rows: list[tuple[str]]
    for (pos,) in rows:
        if pos not in counts:
            raise HTTPException(status_code=400, detail=f"Invalid player position in market: {pos}")
        counts[pos] += 1
    return counts



def _is_feasible_with_counts(counts: dict[str, int], remaining_slots: int) -> bool:
    # ¿Puedo llegar a los mínimos con los huecos que me quedan?
    missing = 0
    for pos, min_req in MIN_BY_POSITION.items():
        missing += max(0, min_req - int(counts.get(pos, 0)))
    return missing <= remaining_slots


def _allowed_positions_now(db: Session, draft_ids: set[str]) -> set[str]:
    # Con el draft actual, ¿qué posiciones puedo fichar ahora mismo?
    current_count = len(draft_ids)
    remaining_slots = MAX_PLAYERS - current_count
    if remaining_slots <= 0:
        return set()

    counts = _count_positions_for_ids(db, draft_ids)

    allowed = set()
    for pos in ALL_POSITIONS:
        new_counts = dict(counts)
        new_counts[pos] += 1
        # tras fichar 1 jugador, quedan remaining_slots-1
        if _is_feasible_with_counts(new_counts, remaining_slots - 1):
            allowed.add(pos)

    return allowed


def _enforce_position_rules_on_add(db: Session, draft_ids: set[str], player_to_add: MarketPlayerPrice):
    allowed = _allowed_positions_now(db, draft_ids)
    if player_to_add.position not in allowed:
        # Mensaje “útil” como el que quieres tú
        allowed_txt = ", ".join(sorted(allowed)) if allowed else "NONE"
        raise HTTPException(
            status_code=400,
            detail=f"With your current roster structure, you can only sign: {allowed_txt}",
        )


def _enforce_final_roster_positions(db: Session, draft_ids: set[str]):
    # Para validación final (init_team / freeze / commit): con 10 jugadores, que cumpla mínimos.
    counts = _count_positions_for_ids(db, draft_ids)
    for pos, min_req in MIN_BY_POSITION.items():
        if counts[pos] < min_req:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid roster: need at least {min_req} {pos} (you have {counts[pos]})",
            )

def _get_or_create_state(db: Session, user_id: int) -> UserSeasonState:
    st = db.query(UserSeasonState).filter_by(user_id=user_id, season_id=SEASON_ID).first()
    if st:
        return st
    season_state = get_or_create_season_state(db)
    st = UserSeasonState(
        user_id=user_id,
        season_id=SEASON_ID,
        budget_base=INITIAL_BUDGET,
        budget_current=INITIAL_BUDGET,
        changes_used_total=0,
        is_preseason=1 if season_state.is_preseason else 0,
    )
    db.add(st)
    db.commit()
    db.refresh(st)
    return st

def _get_roster_ids(db: Session, user_id: int, table):
    rows = db.query(table).filter_by(user_id=user_id, season_id=SEASON_ID).all()
    return {r.player_id for r in rows}

def _ensure_rosters_initialized(db: Session, user_id: int):
    # Ya no auto-sincronizamos base <-> draft.
    # Permitimos draft vacío (sobre todo en pretemporada).
    return

def _count_changes_this_week(base_ids: set, draft_ids: set) -> int:
    # Como siempre son 10, esto equivale al nº de jugadores que han salido
    return len(base_ids - draft_ids)

def _validate_max_per_real_team(db: Session, draft_ids: set):
    # cuenta team_name en el draft
    team_counts = {}
    for pid in draft_ids:
        mp = db.query(MarketPlayerPrice).filter_by(season_id=SEASON_ID, player_id=pid).first()
        if not mp:
            raise HTTPException(status_code=404, detail=f"Player {pid} not found in market")
        team_counts[mp.team_id] = team_counts.get(mp.team_id, 0) + 1
        if team_counts[mp.team_id] > MAX_PER_REAL_TEAM:
            raise HTTPException(status_code=400, detail="Max 2 players per real team")
        

def _get_active_round_or_0(ms) -> int:
    return int(ms.active_round or 0)

def _draft_count(db: Session, user_id: int) -> int:
    return db.query(UserRosterDraft).filter_by(user_id=user_id, season_id=SEASON_ID).count()

def _is_user_frozen_for_round(st: UserSeasonState, active_round: int) -> bool:
    return (active_round > 0) and (st.last_frozen_round == active_round)

def _freeze_user_if_ready(db: Session, user_id: int, active_round: int):
    """
    Congela a ESTE usuario si ya ha restaurado 10 jugadores durante mercado cerrado.
    - base <- draft
    - budget_base <- budget_current
    - si no es preseason: sumar cambios al total
    - last_frozen_round <- active_round
    - si captain es NULL, autoselecciona uno (primer player_id ordenado)
    """
    if active_round <= 0:
        return

    st = db.query(UserSeasonState).filter_by(user_id=user_id, season_id=SEASON_ID).first()
    if not st or st.last_frozen_round == active_round:
        return

    draft_rows = db.query(UserRosterDraft).filter_by(user_id=user_id, season_id=SEASON_ID).all()
    draft_ids = [r.player_id for r in draft_rows]
    if len(draft_ids) != MAX_PLAYERS:
        return  # aún no está completo
    
    _enforce_final_roster_positions(db, set(draft_ids))

    # capitán: si no hay, autoselecciona uno determinista
    cap = db.query(UserCaptain).filter_by(user_id=user_id, season_id=SEASON_ID).first()
    if not cap:
        db.add(UserCaptain(user_id=user_id, season_id=SEASON_ID, captain_player_id=sorted(draft_ids)[0]))
    else:
        if not cap.captain_player_id:
            cap.captain_player_id = sorted(draft_ids)[0]

    base_ids = _get_roster_ids(db, user_id, UserRosterBase)

    # Contar cambios solo cuando se congela y roster ya es 10
    changes_this_week = len(base_ids - set(draft_ids))

    # Reemplazar base por draft
    db.query(UserRosterBase).filter_by(user_id=user_id, season_id=SEASON_ID).delete()
    db.add_all([UserRosterBase(user_id=user_id, season_id=SEASON_ID, player_id=pid) for pid in draft_ids])

    st.budget_base = st.budget_current

    # Preseason: no computa cambios; temporada: sí
    season_state = get_or_create_season_state(db)
    if not bool(season_state.is_preseason):
        st.changes_used_total = int(st.changes_used_total or 0) + int(changes_this_week)

    st.last_frozen_round = active_round
    db.commit()

def _guard_market_for_action(
    db: Session,
    user_id: int,
    action: str,  # "ADD" | "UNDO" | "REMOVE" | "RESET" | "CAPTAIN"
):
    """
    Reglas:
    - Si mercado abierto => OK para todo.
    - Si mercado cerrado:
        - Si usuario ya congelado para esa ronda => prohibido para todo.
        - Si no congelado:
            - REMOVE y RESET siempre prohibidos
            - CAPTAIN prohibido
            - ADD/UNDO solo permitidos si draft_count < 10 (reparación)
    """
    commit_round_if_needed(db)
    ms = compute_market_status(db)
    active_round = _get_active_round_or_0(ms)

    st = _get_or_create_state(db, user_id)

    if ms.is_open:
        return ms, active_round, st  # normal

    # mercado cerrado
    if _is_user_frozen_for_round(st, active_round):
        raise HTTPException(status_code=403, detail="Market is closed (team already frozen)")

    if action in ("REMOVE", "CAPTAIN", "RESET"):
        raise HTTPException(status_code=403, detail="Market is closed")

    # ADD / UNDO : solo si hay huecos
    cnt = _draft_count(db, user_id)
    if cnt >= MAX_PLAYERS:
        raise HTTPException(status_code=403, detail="Market is closed")

    return ms, active_round, st



@router.get("/team")
def my_team(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    season_state = get_or_create_season_state(db)
    st = _get_or_create_state(db, user.user_id)
    _ensure_rosters_initialized(db, user.user_id)

    base_ids = _get_roster_ids(db, user.user_id, UserRosterBase)
    draft_ids = _get_roster_ids(db, user.user_id, UserRosterDraft)

    if not base_ids and not draft_ids:
        return {
            "season_id": SEASON_ID,
            "budget": st.budget_current,
            "changes_used_total": st.changes_used_total,
            "changes_this_week": 0,
            "changes_left_total": max(0, MAX_TOTAL_CHANGES - st.changes_used_total),
            "is_preseason": bool(season_state.is_preseason),
            "captain_player_id": None,
            "players": [],
            "count": 0,
            "needs_initial_team": True,
        }

    changes_this_week = _count_changes_this_week(base_ids, draft_ids)

    # Traer info de mercado para mostrar roster draft
    draft_players = []
    for pid in sorted(draft_ids):
        mp = db.query(MarketPlayerPrice).filter_by(season_id=SEASON_ID, player_id=pid).first()
        if mp:
            draft_players.append({
                "player_id": mp.player_id,
                "name": mp.name,
                "position": mp.position,
                "team_name": mp.team_name,
                "price": mp.price_current,
            })
        else:
            draft_players.append({"player_id": pid, "name": "UNKNOWN", "position": "?", "team_name": "?", "price": None})

    cap = db.query(UserCaptain).filter_by(user_id=user.user_id, season_id=SEASON_ID).first()

    return {
        "season_id": SEASON_ID,
        "budget": st.budget_current,
        "changes_used_total": st.changes_used_total,
        "changes_this_week": changes_this_week,
        "changes_left_total": max(0, MAX_TOTAL_CHANGES - st.changes_used_total),
        "is_preseason": bool(season_state.is_preseason),
        "captain_player_id": cap.captain_player_id if cap else None,
        "players": draft_players,
        "count": len(draft_players),
    }

@router.post("/captain")
def set_captain(req: CaptainRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ms, active_round, st = _guard_market_for_action(db, user.user_id, action="CAPTAIN")

    draft_ids = _get_roster_ids(db, user.user_id, UserRosterDraft)
    if req.player_id not in draft_ids:
        raise HTTPException(status_code=400, detail="Captain must be in your current team")

    cap = db.query(UserCaptain).filter_by(user_id=user.user_id, season_id=SEASON_ID).first()
    if cap:
        cap.captain_player_id = req.player_id
    else:
        db.add(UserCaptain(user_id=user.user_id, season_id=SEASON_ID, captain_player_id=req.player_id))

    db.commit()
    return {"ok": True, "captain_player_id": req.player_id}

@router.post("/team/init")
def init_team(req: InitTeamRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = _get_or_create_state(db, user.user_id)

    # ya inicializado?
    base_ids = _get_roster_ids(db, user.user_id, UserRosterBase)
    draft_ids = _get_roster_ids(db, user.user_id, UserRosterDraft)
    if base_ids or draft_ids:
        raise HTTPException(status_code=400, detail="Team already initialized")

    ids = req.player_ids

    if len(ids) != MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Initial team must have exactly 10 players")

    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Duplicate player_id in initial team")

    # validar mercado + sumar precios
    players = (
        db.query(MarketPlayerPrice)
        .filter(MarketPlayerPrice.season_id == SEASON_ID, MarketPlayerPrice.player_id.in_(ids))
        .all()
    )
    if len(players) != MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="One or more player_id not found in market")

    total_cost = sum(p.price_current for p in players)
    if total_cost > st.budget_current:
        raise HTTPException(status_code=400, detail="Not enough budget for initial team")

    # max 2 por equipo real
    team_counts = {}
    for p in players:
        team_counts[p.team_id] = team_counts.get(p.team_id, 0) + 1
        if team_counts[p.team_id] > MAX_PER_REAL_TEAM:
            raise HTTPException(status_code=400, detail="Max 2 players per real team")
        
    # --- Validación FINAL por puestos (equipo inicial ya completo) ---
    _enforce_final_roster_positions(db, set(ids))


    # guardar base y draft iguales
    db.add_all([UserRosterBase(user_id=user.user_id, season_id=SEASON_ID, player_id=pid) for pid in ids])
    db.add_all([UserRosterDraft(user_id=user.user_id, season_id=SEASON_ID, player_id=pid) for pid in ids])

    # descontar presupuesto (equipo inicial cuesta presupuesto, pero no cuenta como cambios)
    st.budget_current -= total_cost

    db.commit()
    return {"ok": True, "budget": st.budget_current}

@router.post("/team/add")
def add_player(req: PlayerIdRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ms, active_round, st = _guard_market_for_action(db, user.user_id, action="ADD")

    draft_ids = _get_roster_ids(db, user.user_id, UserRosterDraft)

    if req.player_id in draft_ids:
        raise HTTPException(status_code=400, detail="Player already in your current team")

    if len(draft_ids) >= MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Team is full (10 players)")

    mp = db.query(MarketPlayerPrice).filter_by(season_id=SEASON_ID, player_id=req.player_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Player not found in market")

    if st.budget_current < mp.price_current:
        raise HTTPException(status_code=400, detail="Not enough budget")

    # simular draft final y validar max 2 por equipo real
    new_draft_ids = set(draft_ids)
    new_draft_ids.add(req.player_id)
    _validate_max_per_real_team(db, new_draft_ids)

    # --- Validación dinámica por puestos ---
    _enforce_position_rules_on_add(db, draft_ids, mp)

    # aplicar
    db.add(UserRosterDraft(user_id=user.user_id, season_id=SEASON_ID, player_id=req.player_id))
    st.budget_current -= mp.price_current

    # log acción (para undo)
    db.add(UserDraftAction(user_id=user.user_id, season_id=SEASON_ID, action="ADD", player_id=req.player_id))

    db.commit()

    # si mercado estaba cerrado, puede que acabemos de completar 10 -> congelar ahora
    if not ms.is_open:
        _freeze_user_if_ready(db, user.user_id, active_round)

    return {"ok": True, "budget": st.budget_current, "count": len(new_draft_ids)}

@router.post("/team/remove")
def remove_player(req: PlayerIdRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ms, active_round, st = _guard_market_for_action(db, user.user_id, action="REMOVE")

    # 1) comprobar existe en mercado (para precio), y comprobar que no es el capitán
    mp = db.query(MarketPlayerPrice).filter_by(season_id=SEASON_ID, player_id=req.player_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Player not found in market")
    
    cap = db.query(UserCaptain).filter_by(user_id=user.user_id, season_id=SEASON_ID).first()
    if cap and cap.captain_player_id == req.player_id:
        raise HTTPException(status_code=400, detail="You must change captain before removing the current captain")
    
    # 2) borrar de draft de forma robusta
    q = db.query(UserRosterDraft).filter_by(
        user_id=user.user_id, season_id=SEASON_ID, player_id=req.player_id
    )
    deleted = q.delete(synchronize_session=False)

    if deleted == 0:
        # no estaba en draft -> no hay dinero gratis
        raise HTTPException(status_code=404, detail="Player not in your current team")

    # 3) sumar presupuesto
    st.budget_current += mp.price_current

    # 4) log acción para undo
    db.add(UserDraftAction(user_id=user.user_id, season_id=SEASON_ID, action="REMOVE", player_id=req.player_id))

    db.commit()

    # 5) devolver count real
    new_count = db.query(UserRosterDraft).filter_by(user_id=user.user_id, season_id=SEASON_ID).count()
    return {"ok": True, "budget": st.budget_current, "count": new_count}

@router.post("/team/reset_all")
def reset_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ms, active_round, st = _guard_market_for_action(db, user.user_id, action="RESET")

    base_ids = _get_roster_ids(db, user.user_id, UserRosterBase)

    db.query(UserRosterDraft).filter_by(user_id=user.user_id, season_id=SEASON_ID).delete()
    if base_ids:
        db.add_all([UserRosterDraft(user_id=user.user_id, season_id=SEASON_ID, player_id=pid) for pid in base_ids])

    st.budget_current = st.budget_base

    cap = db.query(UserCaptain).filter_by(user_id=user.user_id, season_id=SEASON_ID).first()
    if cap and cap.captain_player_id not in base_ids:
        db.delete(cap)

    db.query(UserDraftAction).filter_by(user_id=user.user_id, season_id=SEASON_ID).delete()

    db.commit()
    return {"ok": True, "budget": st.budget_current, "count": len(base_ids)}

@router.post("/team/undo_remove")
def undo_remove(req: PlayerIdRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ms, active_round, st = _guard_market_for_action(db, user.user_id, action="UNDO")

    # ya está en el draft? entonces nada que recuperar
    draft_ids = _get_roster_ids(db, user.user_id, UserRosterDraft)
    if req.player_id in draft_ids:
        raise HTTPException(status_code=400, detail="Player is already in your current team")

    # comprobar última acción de ese jugador
    last = (
        db.query(UserDraftAction)
        .filter_by(user_id=user.user_id, season_id=SEASON_ID, player_id=req.player_id)
        .order_by(UserDraftAction.id.desc())
        .first()
    )
    if not last or last.action != "REMOVE":
        raise HTTPException(status_code=400, detail="This player was not removed in the current market session")

    if len(draft_ids) >= MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Team is full (10 players)")

    mp = db.query(MarketPlayerPrice).filter_by(season_id=SEASON_ID, player_id=req.player_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Player not found in market")

    if st.budget_current < mp.price_current:
        raise HTTPException(status_code=400, detail="Not enough budget to restore this player")

    # validar max 2 por equipo real con el draft resultante
    new_draft_ids = set(draft_ids)
    new_draft_ids.add(req.player_id)
    _validate_max_per_real_team(db, new_draft_ids)

    # --- Validación dinámica por puestos ---
    _enforce_position_rules_on_add(db, draft_ids, mp)

    # aplicar: re-añadir al draft + ajustar presupuesto
    db.add(UserRosterDraft(user_id=user.user_id, season_id=SEASON_ID, player_id=req.player_id))
    st.budget_current -= mp.price_current

    # registrar acción (opcional, pero útil para trazabilidad)
    db.add(UserDraftAction(user_id=user.user_id, season_id=SEASON_ID, action="ADD", player_id=req.player_id))

    db.commit()

    if not ms.is_open:
        _freeze_user_if_ready(db, user.user_id, active_round)

    return {"ok": True, "budget": st.budget_current, "count": len(new_draft_ids)}
