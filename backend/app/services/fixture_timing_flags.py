from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from sqlalchemy.orm import Session

from app.models.fixtures import Fixture


def recompute_flags_roundcentric(
    db: Session,
    *,
    season_id: str,
    tol_minutes: int = 0,  # optional tolerance (set later if you want)
) -> dict:
    tol = timedelta(minutes=tol_minutes)

    # Only fixtures with kickoff_at can be classified
    rows = (
        db.query(Fixture)
        .filter(Fixture.season_id == season_id)
        .all()
    )

    # Reset flags first (and we'll re-assign)
    for f in rows:
        f.is_advanced = False
        f.is_postponed = False

    # Group by round (only for those with kickoff)
    by_round: dict[int, list[Fixture]] = defaultdict(list)
    for f in rows:
        if f.kickoff_at is not None:
            by_round[f.round_number].append(f)

    rounds = sorted(by_round.keys())
    if not rounds:
        db.commit()
        return {"updated": 0, "advanced": 0, "postponed": 0, "note": "no kickoff_at rows"}

    # Helper: first kickoff of a round (min)
    def round_first(r: int):
        xs = [f.kickoff_at for f in by_round.get(r, []) if f.kickoff_at is not None]
        return min(xs) if xs else None

    # -------------------------
    # PASS 1: ADVANCED
    # Rule c) Round N is advanced if ANY fixture in N starts before FIRST fixture of N-1
    # -------------------------
    advanced_ids: set[int] = set()

    first_by_round = {r: round_first(r) for r in rounds}

    for r in rounds:
        prev = r - 1
        prev_first = first_by_round.get(prev)
        if prev_first is None:
            continue

        for f in by_round[r]:
            if f.kickoff_at is None:
                continue
            if f.kickoff_at < (prev_first - tol):
                advanced_ids.add(f.id)

    for f in rows:
        f.is_advanced = (f.id in advanced_ids)

    # -------------------------
    # PASS 2: POSTPONED
    # Rule e) Round N is postponed if ANY fixture in N starts after FIRST NON-ADVANCED fixture of N+1
    # -------------------------
    # Compute "first non-advanced kickoff" for each round
    first_non_advanced_by_round: dict[int, object] = {}
    for r in rounds:
        times = [
            f.kickoff_at
            for f in by_round[r]
            if (f.kickoff_at is not None and f.id not in advanced_ids)
        ]
        first_non_advanced_by_round[r] = min(times) if times else None

    postponed_ids: set[int] = set()

    for r in rounds:
        nxt = r + 1
        nxt_first_non_adv = first_non_advanced_by_round.get(nxt)
        if nxt_first_non_adv is None:
            continue

        for f in by_round[r]:
            if f.kickoff_at is None:
                continue
            if f.kickoff_at > (nxt_first_non_adv + tol):
                postponed_ids.add(f.id)

    for f in rows:
        f.is_postponed = (f.id in postponed_ids)

    db.commit()
    return {
        "updated": len(rows),
        "advanced": len(advanced_ids),
        "postponed": len(postponed_ids),
        "tol_minutes": tol_minutes,
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