# app/services/fixture_timing_flags.py
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.fixtures import Fixture

CORE_MIN_COUNT = 5
MIN_GAP_HOURS = 24.0
MAX_ITER = 6


def _group_by_round(fixtures: list[Fixture]) -> dict[int, list[Fixture]]:
    by_round: dict[int, list[Fixture]] = defaultdict(list)
    for g in fixtures:
        by_round[int(g.round_number)].append(g)
    return by_round


def _detect_postponed_ids_core(fixtures_sorted: list[Fixture], *, tol: timedelta) -> set[int]:
    """
    Postponed (robust):
      A game of round r is postponed only if, by the time it happens,
      we have already "established" some later round R>r (core >= CORE_MIN_COUNT)
      earlier in the timeline.
    """
    postponed: set[int] = set()

    # How many games we've seen per round so far (in time order)
    seen_count: dict[int, int] = defaultdict(int)

    # Highest round that has reached core count
    reached_round: Optional[int] = None
    time_reached_round: Optional[object] = None  # datetime, but keep generic

    for g in fixtures_sorted:
        if g.kickoff_at is None:
            continue

        r = int(g.round_number)
        t = g.kickoff_at

        # If we already reached a later round (core-wise), then an earlier round here is postponed
        if reached_round is not None and r < reached_round:
            # optional tolerance: require some actual time separation vs the moment we "reached" that later round
            if time_reached_round is None or (t - time_reached_round) > tol:
                postponed.add(g.id)

        # Update seen count AFTER classification (important: don't use the same game to establish its own round first)
        seen_count[r] += 1

        # Update reached_round only when core threshold is met
        if seen_count[r] >= CORE_MIN_COUNT:
            if reached_round is None or r > reached_round:
                reached_round = r
                time_reached_round = t

    return postponed


def _detect_advanced_ids_core(fixtures_sorted: list[Fixture], *, tol: timedelta) -> set[int]:
    """
    Advanced (robust):
      A game of round r is advanced only if, looking into the future,
      we can "establish" some earlier round R<r (core >= CORE_MIN_COUNT)
      that occurs after this game.
    """
    advanced: set[int] = set()

    future_seen: dict[int, int] = defaultdict(int)

    # Lowest round in the future that has reached core count
    future_reached_round: Optional[int] = None
    time_future_reached: Optional[object] = None

    for g in reversed(fixtures_sorted):
        if g.kickoff_at is None:
            continue

        r = int(g.round_number)
        t = g.kickoff_at

        # If in the future we already reached an earlier round (core-wise), then this higher round is advanced
        if future_reached_round is not None and r > future_reached_round:
            if time_future_reached is None or (time_future_reached - t) > tol:
                advanced.add(g.id)

        # Update future seen count AFTER classification
        future_seen[r] += 1

        # Update future_reached_round only when core threshold is met
        if future_seen[r] >= CORE_MIN_COUNT:
            if future_reached_round is None or r < future_reached_round:
                future_reached_round = r
                time_future_reached = t

    return advanced


def _compute_core_windows_and_gaps(rows: list[Fixture], *, tol: timedelta):
    """
    Core windows computed from UNFLAGGED fixtures only.
    If core_count < CORE_MIN_COUNT => invalid round (skip entirely).
    Also compute gaps between consecutive valid core windows; want >= 24h.
    """
    dated = [g for g in rows if g.kickoff_at is not None]
    by_round = _group_by_round(dated)

    core_windows: dict[int, dict] = {}
    invalid_core_rounds: list[dict] = []

    for r, fx in sorted(by_round.items()):
        core = [g for g in fx if (not g.is_advanced and not g.is_postponed)]
        if len(core) < CORE_MIN_COUNT:
            invalid_core_rounds.append({
                "round": r,
                "core_count": len(core),
                "dated_count": len(fx),
                "rule": f"core_count < {CORE_MIN_COUNT} => round invalid/skip",
            })
            continue

        start = min(g.kickoff_at for g in core)
        end = max(g.kickoff_at for g in core)
        core_windows[r] = {"round": r, "start": start, "end": end, "count": len(core)}

    gap_warnings: list[dict] = []
    valid_rounds = sorted(core_windows.keys())

    tol_hours = tol.total_seconds() / 3600.0
    min_gap = MIN_GAP_HOURS - tol_hours

    for i in range(len(valid_rounds) - 1):
        r1 = valid_rounds[i]
        r2 = valid_rounds[i + 1]
        end1 = core_windows[r1]["end"]
        start2 = core_windows[r2]["start"]
        gap_hours = (start2 - end1).total_seconds() / 3600.0

        if gap_hours < min_gap:
            gap_warnings.append({
                "round_from": r1,
                "round_to": r2,
                "gap_hours": round(gap_hours, 2),
                "min_required_hours": round(min_gap, 2),
                "end_from": end1,
                "start_to": start2,
            })

    return core_windows, invalid_core_rounds, gap_warnings


def recompute_flags_roundcentric(
    db: Session,
    *,
    season_id: str,
    tol_minutes: int = 0,
    trim_q: float = 0.10,  # kept for signature compatibility (unused)
) -> dict:
    tol = timedelta(minutes=tol_minutes)

    rows: list[Fixture] = (
        db.query(Fixture)
        .filter(Fixture.season_id == season_id)
        .all()
    )

    # Reset flags
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
            "tol_minutes": tol_minutes,
            "note": "no kickoff_at rows",
            "core_windows": {},
            "invalid_core_rounds": [],
            "gap_warnings": [],
        }

    dated_sorted = sorted(dated, key=lambda g: (g.kickoff_at, int(g.round_number), g.id))

    pool_ids = {g.id for g in dated_sorted}
    postponed_ids: set[int] = set()
    advanced_ids: set[int] = set()

    # Stabilize (because core definitions depend on which games are excluded)
    for _ in range(MAX_ITER):
        pool = [g for g in dated_sorted if g.id in pool_ids]

        # 1) postponed first (safe now because "reached round" requires core>=5)
        post_new = _detect_postponed_ids_core(pool, tol=tol) - postponed_ids
        if post_new:
            postponed_ids |= post_new
            pool_ids -= post_new

        pool = [g for g in dated_sorted if g.id in pool_ids]

        # 2) advanced second (also uses core>=5, so single postponed games won't poison it)
        adv_new = _detect_advanced_ids_core(pool, tol=tol) - advanced_ids
        if adv_new:
            advanced_ids |= adv_new
            pool_ids -= adv_new

        if not post_new and not adv_new:
            break

    # Write flags
    for f in rows:
        f.is_postponed = (f.id in postponed_ids)
        f.is_advanced = (f.id in advanced_ids)

    # Guardrail: no round fully flagged (dated fixtures)
    by_round_dated = _group_by_round(dated)
    rounds_fully_flagged_fixed: list[int] = []
    for r, fx in by_round_dated.items():
        if not fx:
            continue
        flagged = [x for x in fx if x.is_advanced or x.is_postponed]
        if len(flagged) == len(fx):
            rounds_fully_flagged_fixed.append(r)
            fx_sorted = sorted(fx, key=lambda x: (x.kickoff_at, x.id))
            mid = fx_sorted[len(fx_sorted) // 2]
            mid.is_advanced = False
            mid.is_postponed = False
            advanced_ids.discard(mid.id)
            postponed_ids.discard(mid.id)

    # Team sanity report
    team_warnings: list[dict] = []
    for r, fx in sorted(by_round_dated.items()):
        counts = defaultdict(int)
        for g in fx:
            counts[g.home_team_id] += 1
            counts[g.away_team_id] += 1
        not_1 = sorted([t for t, c in counts.items() if c != 1])
        if len(fx) != 9:
            team_warnings.append({"round": r, "games": len(fx), "teams_with_count_not_1": not_1})

    # Core windows and gaps (and invalid rounds)
    core_windows, invalid_core_rounds, gap_warnings = _compute_core_windows_and_gaps(rows, tol=tol)

    db.commit()

    return {
        "updated": len(rows),
        "advanced": len(advanced_ids),
        "postponed": len(postponed_ids),
        "tol_minutes": tol_minutes,
        "rounds_fully_flagged_fixed": rounds_fully_flagged_fixed,
        "team_warnings": team_warnings,
        "core_windows": core_windows,
        "invalid_core_rounds": invalid_core_rounds,
        "gap_warnings": gap_warnings,
        "algo": "core>=5 inversion scan (postponed+advanced stabilized)",
    }