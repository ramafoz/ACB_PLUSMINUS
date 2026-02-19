# scripts/list_fixtures_by_kickoff.py
# Usage:
#   python scripts/list_fixtures_by_kickoff.py acb_game.sqlite 2025-26
#   python scripts/list_fixtures_by_kickoff.py acb_game.sqlite 2025-26 --tsv
#   python scripts/list_fixtures_by_kickoff.py acb_game.sqlite 2025-26 --limit 50

import argparse
import sqlite3
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", help="Path to sqlite DB, e.g. acb_game.sqlite")
    ap.add_argument("season_id", help='Season id, e.g. "2025-26"')
    ap.add_argument("--limit", type=int, default=0, help="Limit rows printed (0 = all)")
    ap.add_argument("--tsv", action="store_true", help="Print as TSV (tab-separated)")
    args = ap.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    sep = "\t" if args.tsv else " | "

    sql = """
    SELECT
        id,
        round_number,
        kickoff_at,
        home_team_id,
        away_team_id,
        is_finished,
        home_score,
        away_score,
        is_advanced,
        is_postponed,
        acb_game_id
    FROM fixtures
    WHERE season_id = ?
    ORDER BY
        CASE WHEN kickoff_at IS NULL THEN 1 ELSE 0 END,
        kickoff_at ASC,
        round_number ASC,
        id ASC;
    """

    with sqlite3.connect(str(db_path)) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, (args.season_id,)).fetchall()

    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    print(
        sep.join([
            "idx", "id", "rnd", "kickoff_at",
            "home", "away",
            "fin", "score",
            "adv", "ppd",
            "acb_game_id",
        ])
    )

    for idx, r in enumerate(rows, start=1):
        hs = r["home_score"]
        a_s = r["away_score"]
        score = f"{hs}-{a_s}" if (hs is not None and a_s is not None) else ""

        print(
            sep.join([
                str(idx),
                str(r["id"]),
                str(r["round_number"]),
                str(r["kickoff_at"] or ""),
                str(r["home_team_id"]),
                str(r["away_team_id"]),
                "1" if r["is_finished"] else "0",
                score,
                "1" if r["is_advanced"] else "0",
                "1" if r["is_postponed"] else "0",
                str(r["acb_game_id"] or ""),
            ])
        )

    print(f"\nTOTAL: {len(rows)} row(s) printed for season {args.season_id}")

if __name__ == "__main__":
    main()
