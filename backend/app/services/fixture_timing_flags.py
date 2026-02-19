# app/services/fixture_timing_flags.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.fixtures import Fixture


# ============================
# Core concept (your definition)
# ============================
# We work on the GLOBAL schedule ordered by kickoff_at.
#
# A "core" for a round = the largest contiguous block of that round
# after removing already-flagged intruders.
#
# Outliers (fixtures of that round not in its core) are flagged:
#   - advanced  if they occur before the core
#   - postponed if they occur after the core
#
# We "peel" intruders iteratively until stable.
#
# Extra rules you requested:
# - If len(core) < 5 => the round is NOT valid for the fantasy game; skip it entirely
#   (returned in rounds_incomplete; we do NOT try to solve that round further).
# - Compute the time gap between consecutive cores; warn if < 24h.


MIN_CORE = 5
MIN_CORE_GAP_HOURS = 24
MAX_ITERS = 15


def _sorted_rows(rows: List[Fixture]) -> List[Fixture]:
    # Stable ordering: kickoff_at, then id
    return sorted(rows, key=lambda f: (f.kickoff_at, f.id))


def _compute_runs(schedule: List[Fixture]) -> Dict[int, List[Tuple[int, int]]]:
    """
    Returns runs per round: {round: [(i0,i1), ...]} where i0..i1 are contiguous indices
    in the provided schedule list.
    """
    runs: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    i = 0
    n = len(schedule)
    while i < n:
        r = schedule[i].round_number
        j = i
        while j + 1 < n and schedule[j + 1].round_number == r:
            j += 1
        runs[r].append((i, j))
        i = j + 1
    return runs


def _pick_largest_run(runs_for_round: List[Tuple[int, int]]) -> Tuple[int, int, int]:
    """
    Returns (start_idx, end_idx, length) of the largest run.
    """
    best = None
    for a, b in runs_for_round:
        ln = b - a + 1
        if best is None or ln > best[2]:
            best = (a, b, ln)
    assert best is not None
    return best


def _compute_core_map(schedule: List[Fixture]) -> Tuple[Dict[int, Set[int]], Set[int]]:
    """
    For the provided schedule (already filtered for unflagged fixtures),
    compute:
      - core_ids_by_round: round -> set(fixture_id) for its core run (if len>=MIN_CORE)
      - rounds_incomplete: rounds whose largest run is < MIN_CORE
    """
    runs = _compute_runs(schedule)

    core_ids_by_round: Dict[int, Set[int]] = {}
    rounds_incomplete: Set[int] = set()

    for r, rruns in runs.items():
        a, b, ln = _pick_largest_run(rruns)
        if ln < MIN_CORE:
            rounds_incomplete.add(r)
            continue
        core_ids_by_round[r] = {schedule[i].id for i in range(a, b + 1)}

    return core_ids_by_round, rounds_incomplete


def _classify_outliers(
    schedule: List[Fixture],
    core_ids_by_round: Dict[int, Set[int]],
) -> Tuple[Set[int], Set[int]]:
    """
    Given schedule and core map, return (advanced_ids, postponed_ids) to flag.
    Only rounds that have a valid core (len>=MIN_CORE) participate.
    """
    advanced_ids: Set[int] = set()
    postponed_ids: Set[int] = set()

    # Precompute core time windows for classification
    core_window: Dict[int, Tuple[datetime, datetime]] = {}
    for r, core_ids in core_ids_by_round.items():
        core_rows = [f for f in schedule if f.id in core_ids]
        if not core_rows:
            continue
        core_start = min(f.kickoff_at for f in core_rows)
        core_end = max(f.kickoff_at for f in core_rows)
        core_window[r] = (core_start, core_end)

    for f in schedule:
        r = f.round_number
        if r not in core_ids_by_round:
            # incomplete rounds are not processed here
            continue

        if f.id in core_ids_by_round[r]:
            continue  # inside core

        # outlier
        core_start, core_end = core_window[r]
        if f.kickoff_at < core_start:
            advanced_ids.add(f.id)
        elif f.kickoff_at > core_end:
            postponed_ids.add(f.id)
        else:
            # Rare: same datetime window but separated by intruders.
            # Resolve by position relative to the core run indices.
            # (If it is not in the core set, it must be outside the core run.)
            advanced_ids.add(f.id)  # safe fallback; but we can do better:

            # Better fallback: find first/last core index for this round
            idxs = [i for i, x in enumerate(schedule) if x.id in core_ids_by_round[r]]
            if idxs:
                core_i0, core_i1 = min(idxs), max(idxs)
                my_i = next(i for i, x in enumerate(schedule) if x.id == f.id)
                if my_i < core_i0:
                    advanced_ids.add(f.id)
                    postponed_ids.discard(f.id)
                elif my_i > core_i1:
                    postponed_ids.add(f.id)
                    advanced_ids.discard(f.id)

    return advanced_ids, postponed_ids


def _compute_core_gaps_hours(
    schedule: List[Fixture],
    core_ids_by_round: Dict[int, Set[int]],
) -> List[dict]:
    """
    Computes the time gap (hours) between consecutive round cores,
    ordered by round number (not by datetime).
    """
    # Build core start/end for each round
    core_bounds: Dict[int, Tuple[datetime, datetime]] = {}
    for r, ids in core_ids_by_round.items():
        core_rows = [f for f in schedule if f.id in ids]
        if not core_rows:
            continue
        core_bounds[r] = (min(f.kickoff_at for f in core_rows), max(f.kickoff_at for f in core_rows))

    out: List[dict] = []
    rounds = sorted(core_bounds.keys())
    for i in range(len(rounds) - 1):
        r1 = rounds[i]
        r2 = rounds[i + 1]
        end1 = core_bounds[r1][1]
        start2 = core_bounds[r2][0]
        gap_h = (start2 - end1).total_seconds() / 3600.0
        out.append(
            {
                "round_from": r1,
                "round_to": r2,
                "gap_hours": gap_h,
                "ok_ge_24h": gap_h >= float(MIN_CORE_GAP_HOURS),
                "end_from": end1,
                "start_to": start2,
            }
        )
    return out


def recompute_flags_roundcentric(
    db: Session,
    *,
    season_id: str,
    tol_minutes: int = 0,  # kept for API compatibility; not used here
    trim_q: float = 0.10,  # kept for API compatibility; not used here
) -> dict:
    """
    Recompute is_advanced/is_postponed using the "peel intruders until stable" algorithm.
    """

    rows: List[Fixture] = (
        db.query(Fixture)
        .filter(Fixture.season_id == season_id)
        .all()
    )

    # Reset flags first
    for f in rows:
        f.is_advanced = False
        f.is_postponed = False

    dated = [f for f in rows if f.kickoff_at is not None]
    if not dated:
        db.commit()
        return {
            "updated": len(rows),
            "advanced": 0,
            "postponed": 0,
            "rounds_incomplete": [],
            "core_gaps": [],
            "note": "no kickoff_at rows",
        }

    base_schedule = _sorted_rows(dated)

    flagged: Set[int] = set()
    advanced_ids: Set[int] = set()
    postponed_ids: Set[int] = set()

    rounds_incomplete_final: Set[int] = set()
    core_ids_by_round_final: Dict[int, Set[int]] = {}

    for _ in range(MAX_ITERS):
        # Build schedule excluding currently flagged fixtures
        schedule = [f for f in base_schedule if f.id not in flagged]

        core_ids_by_round, rounds_incomplete = _compute_core_map(schedule)

        # Keep latest view (the stable one is what we want at the end)
        rounds_incomplete_final = set(rounds_incomplete)
        core_ids_by_round_final = {r: set(ids) for r, ids in core_ids_by_round.items()}

        new_adv, new_ppd = _classify_outliers(schedule, core_ids_by_round)

        newly_flagged = (new_adv | new_ppd) - flagged
        if not newly_flagged:
            break

        flagged |= newly_flagged
        advanced_ids |= new_adv
        postponed_ids |= new_ppd

    # Write flags
    for f in rows:
        f.is_advanced = (f.id in advanced_ids)
        f.is_postponed = (f.id in postponed_ids)

    db.commit()

    # Compute core gaps on the final "cleaned" schedule
    final_schedule = [f for f in base_schedule if f.id not in flagged]
    core_gaps = _compute_core_gaps_hours(final_schedule, core_ids_by_round_final)

    return {
        "updated": len(rows),
        "advanced": len(advanced_ids),
        "postponed": len(postponed_ids),
        "rounds_incomplete": sorted(list(rounds_incomplete_final)),
        "core_gaps": core_gaps,
        "min_core": MIN_CORE,
        "min_core_gap_hours": MIN_CORE_GAP_HOURS,
    }