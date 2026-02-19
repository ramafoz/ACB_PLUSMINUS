# scripts/reset_fixture_flags.py
# Usage:
#   python scripts/reset_fixture_flags.py acb_game.sqlite 2025-26
#   python scripts/reset_fixture_flags.py acb_game.sqlite 2025-26 --only-unfinished

import argparse
import sqlite3
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", help="Path to sqlite db, e.g. acb_game.sqlite")
    ap.add_argument("season_id", help='Season id, e.g. "2025-26"')
    ap.add_argument("--only-unfinished", action="store_true",
                    help="Only reset flags for fixtures not finished yet")
    args = ap.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    where_extra = " AND is_finished = 0" if args.only_unfinished else ""
    sql = f"""
    UPDATE fixtures
    SET is_postponed = 0,
        is_advanced  = 0
    WHERE season_id = ?
      AND (is_postponed = 1 OR is_advanced = 1)
      {where_extra};
    """

    with sqlite3.connect(str(db_path)) as con:
        cur = con.cursor()
        cur.execute(sql, (args.season_id,))
        changed = cur.rowcount
        con.commit()

    print(f"DONE. Reset flags to False for {changed} fixture(s) in season {args.season_id}.")

if __name__ == "__main__":
    main()