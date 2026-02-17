# app/services/fixture_flags.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, Dict, List, Tuple, Optional

def compute_flags_for_season(
    fixtures: Iterable[Tuple[int, str, str, Optional[datetime]]]
) -> Dict[Tuple[int, str, str], Tuple[bool, bool]]:
    """
    Input: iterable of (round_number, home_team_id, away_team_id, kickoff_at)
    Output: dict keyed by (round, home, away) -> (is_postponed, is_advanced)
    """
    by_round: Dict[int, List[datetime]] = defaultdict(list)

    # collect kickoffs per round
    for rnd, h, a, ko in fixtures:
        if ko is not None:
            by_round[rnd].append(ko)

    # precompute min/max per round
    round_min: Dict[int, datetime] = {}
    round_max: Dict[int, datetime] = {}
    for rnd, kos in by_round.items():
        if kos:
            round_min[rnd] = min(kos)
            round_max[rnd] = max(kos)

    # compute per fixture
    out: Dict[Tuple[int, str, str], Tuple[bool, bool]] = {}

    for rnd, h, a, ko in fixtures:
        is_postponed = False
        is_advanced = False

        if ko is not None:
            # postponed if after next round starts
            next_min = round_min.get(rnd + 1)
            if next_min is not None and ko > next_min:
                is_postponed = True

            # advanced if before previous round ends
            prev_max = round_max.get(rnd - 1)
            if prev_max is not None and ko < prev_max:
                is_advanced = True

        out[(rnd, h, a)] = (is_postponed, is_advanced)

    return out
