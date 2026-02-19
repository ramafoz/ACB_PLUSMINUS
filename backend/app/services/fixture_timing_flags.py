from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from sqlalchemy.orm import Session

from app.models.fixtures import Fixture


def recompute_flags_roundcentric(
    db: Session,
    *,
    season_id: str,
    tol_minutes: int = 0,
) -> dict:
    """
    Neighbor-based flagging (your algorithm):
      a) get all fixtures (with kickoff_at)
      b) order by kickoff_at
      c) for fixture n: if n+1 has LOWER round and n+1 is NOT postponed -> flag n as advanced
      d) for fixture n: if n-1 has HIGHER round and n-1 is NOT advanced  -> flag n as postponed
      e) never allow flagging to consume an entire round (keep at least 1 unflagged per round)
      f) optional sanity: teams-per-round check reported as warnings (no DB changes)

    Notes:
    - Uses a tolerance window: if two games are within tol, we treat them as "same time" and do not infer.
    - Excludes fixtures with kickoff_at NULL from the ordering/logic.
    """
    tol = timedelta(minutes=tol_minutes)

    rows = (
        db.query(Fixture)
        .filter(Fixture.season_id == season_id)
        .all()
    )

    # Reset flags first
    for f in rows:
        f.is_advanced = False
        f.is_postponed = False

    # Work only with dated fixtures
    dated = [f for f in rows if f.kickoff_at is not None]
    if not dated:
        db.commit()
        return {"updated": len(rows), "advanced": 0, "postponed": 0, "tol_minutes": tol_minutes, "note": "no kickoff_at rows"}

    dated.sort(key=lambda f: (f.kickoff_at, f.round_number, f.id))

    # PASS 1: ADVANCED (based on next neighbor)
    advanced_ids: set[int] = set()
    for i, f in enumerate(dated):
        if i == len(dated) - 1:
            continue
        nxt = dated[i + 1]

        # If times are essentially the same, don't infer
        if tol_minutes > 0 and abs(nxt.kickoff_at - f.kickoff_at) <= tol:
            continue

        # If next game belongs to an earlier round, current looks "advanced"
        if nxt.round_number < f.round_number and not nxt.is_postponed:
            advanced_ids.add(f.id)

    for f in rows:
        f.is_advanced = (f.id in advanced_ids)

    # PASS 2: POSTPONED (based on previous neighbor)
    postponed_ids: set[int] = set()
    for i, f in enumerate(dated):
        if i == 0:
            continue
        prv = dated[i - 1]

        if tol_minutes > 0 and abs(f.kickoff_at - prv.kickoff_at) <= tol:
            continue

        # If previous game belongs to a later round, current looks "postponed"
        if prv.round_number > f.round_number and not prv.is_advanced:
            postponed_ids.add(f.id)

    for f in rows:
        f.is_postponed = (f.id in postponed_ids)

    # GUARDRAIL e): flagged fixtures could never be all fixtures from a round
    # Keep at least one unflagged game per round (prefer unflagging games closest to the "core" of the round)
    by_round: dict[int, list[Fixture]] = defaultdict(list)
    for f in dated:
        by_round[f.round_number].append(f)

    rounds_fully_flagged = []
    for r, fx in by_round.items():
        if not fx:
            continue
        flagged = [x for x in fx if x.is_advanced or x.is_postponed]
        if len(flagged) == len(fx):
            rounds_fully_flagged.append(r)
            # unflag one "best candidate" = median kickoff time in that round
            fx_sorted = sorted(fx, key=lambda x: (x.kickoff_at, x.id))
            mid = fx_sorted[len(fx_sorted) // 2]
            mid.is_advanced = False
            mid.is_postponed = False
            # also update sets for accurate counts
            advanced_ids.discard(mid.id)
            postponed_ids.discard(mid.id)

    # Sanity check: every team should appear exactly once per round (18 teams => 9 games)
    # We only report; we don't change DB.
    team_warnings: list[dict] = []
    for r, fx in sorted(by_round.items()):
        teams = []
        for g in fx:
            teams.append(g.home_team_id)
            teams.append(g.away_team_id)
        counts = defaultdict(int)
        for t in teams:
            counts[t] += 1
        missing = []  # can't infer which are missing without the full teams list
        dup = sorted([t for t, c in counts.items() if c != 1])
        # If scheduled games count is weird, record it
        if len(fx) not in (9, 8):  # 8 can happen if a game genuinely missing
            team_warnings.append({"round": r, "games": len(fx), "teams_with_count_not_1": dup})

    db.commit()
    return {
        "updated": len(rows),
        "advanced": len(advanced_ids),
        "postponed": len(postponed_ids),
        "tol_minutes": tol_minutes,
        "rounds_fully_flagged_fixed": rounds_fully_flagged,
        "team_warnings": team_warnings,
    }


def compute_round_brackets(
    db: Session,
    *,
    season_id: str,
) -> list[dict]:
    """
    f) Optional: bracket first and last NON-FLAGGED fixtures for each round.
    Returns list of {round, start, end, count} for non-flagged games with kickoff.
    """
    rows = (
        db.query(Fixture)
        .filter(Fixture.season_id == season_id, Fixture.kickoff_at.isnot(None))
        .all()
    )

    by_round: dict[int, list[Fixture]] = defaultdict(list)
    for f in rows:
        by_round[f.round_number].append(f)

    out: list[dict] = []
    for r in sorted(by_round.keys()):
        xs = [
            f.kickoff_at
            for f in by_round[r]
            if not f.is_advanced and not f.is_postponed and f.kickoff_at is not None
        ]
        if not xs:
            out.append({"round": r, "start": None, "end": None, "count": 0})
            continue
        out.append({"round": r, "start": min(xs), "end": max(xs), "count": len(xs)})
    return out


def find_bracket_intersections(brackets: list[dict]) -> list[tuple]:
    """
    Returns pairs (r1, r2, start1, end1, start2, end2) where brackets intersect.
    """
    # Only rounds with both start/end
    b = [x for x in brackets if x["start"] and x["end"]]
    bad = []
    for i in range(len(b)):
        for j in range(i + 1, len(b)):
            a = b[i]
            c = b[j]
            # intervals [start,end] overlap if startA <= endC and startC <= endA
            if a["start"] <= c["end"] and c["start"] <= a["end"]:
                bad.append((a["round"], c["round"], a["start"], a["end"], c["start"], c["end"]))
    return bad