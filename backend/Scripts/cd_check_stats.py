#!/usr/bin/env python3
import argparse
import os
import sqlite3
from pathlib import Path


def q1(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def rows(cur, sql, params=(), limit=10):
    cur.execute(sql, params)
    return cur.fetchmany(limit)


def main():
    ap = argparse.ArgumentParser(description="Inspect ACB_PLUSMINUS SQLite and verify stats table contents.")
    ap.add_argument("--db", default="backend/acb_game.sqlite", help="Path to sqlite db (default: backend/acb_game.sqlite)")
    ap.add_argument("--season", default=None, help="Filter season_id (e.g. 2025-26)")
    ap.add_argument("--game", default=None, help="Filter acb_game_id (e.g. 104498)")
    ap.add_argument("--player", default=None, help="Filter acb_player_id (e.g. 30001114)")
    ap.add_argument("--limit", type=int, default=10, help="Rows to show per sample query")
    args = ap.parse_args()

    db_path = Path(args.db)

    print("=== DB CHECK ===")
    print("DB:", db_path.resolve())
    if not db_path.exists():
        print("ERROR: DB file not found.")
        print("Tip: run from repo root, or pass --db with an absolute path.")
        raise SystemExit(2)

    print("Size:", os.path.getsize(db_path), "bytes")
    print()

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Tables
    tbls = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print("Tables:", ", ".join(tbls))
    print()

    # Fixtures sanity
    if "fixtures" in tbls:
        fx_count = q1(cur, "SELECT COUNT(*) FROM fixtures")
        seasons = cur.execute("SELECT DISTINCT season_id FROM fixtures ORDER BY season_id").fetchall()
        print(f"fixtures: {fx_count} rows")
        print("fixtures season_id values:", [r[0] for r in seasons])
        sample_games = cur.execute(
            "SELECT id, season_id, round_number, acb_game_id FROM fixtures "
            "WHERE acb_game_id IS NOT NULL ORDER BY id LIMIT 5"
        ).fetchall()
        print("fixtures sample (id, season, round, acb_game_id):")
        for r in sample_games:
            print("  ", tuple(r))
        print()
    else:
        print("WARN: fixtures table not found.")
        print()

    # Stats sanity
    if "game_player_stats" not in tbls:
        print("ERROR: game_player_stats table not found.")
        raise SystemExit(3)

    st_count = q1(cur, "SELECT COUNT(*) FROM game_player_stats")
    print(f"game_player_stats: {st_count} rows")

    seasons_stats = cur.execute(
        "SELECT DISTINCT season_id FROM game_player_stats ORDER BY season_id"
    ).fetchall()
    print("stats season_id values:", [r[0] for r in seasons_stats])
    print()

    # If empty: done
    if st_count == 0:
        print(">>> CONFIRMED: game_player_stats is EMPTY.")
        print("If your scraping endpoint ran without errors, it likely didn't insert rows (or used another DB path).")
        return

    # Build filtered query
    where = []
    params = []

    if args.season:
        where.append("season_id = ?")
        params.append(args.season)
    if args.game:
        where.append("acb_game_id = ?")
        params.append(args.game)
    if args.player:
        where.append("acb_player_id = ?")
        params.append(args.player)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT season_id, acb_game_id, acb_player_id, minutes_seconds, plus_minus, is_started, play_time "
        f"FROM game_player_stats {where_sql} "
        "ORDER BY season_id, acb_game_id, minutes_seconds DESC "
        f"LIMIT {int(args.limit)}"
    )

    print("Sample rows:")
    for r in cur.execute(sql, params).fetchall():
        print("  ", dict(r))


if __name__ == "__main__":
    main()