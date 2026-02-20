#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from pathlib import Path


def guess_db_path() -> Path:
    env_candidates = [
        os.getenv("SQLITE_PATH"),
        os.getenv("DATABASE_PATH"),
        os.getenv("DB_PATH"),
    ]
    for c in env_candidates:
        if c and Path(c).exists():
            return Path(c)

    common = [
        Path("app/db.sqlite"),
        Path("app/app.sqlite"),
        Path("db.sqlite"),
        Path("app/data/db.sqlite"),
        Path("data/db.sqlite"),
    ]
    for c in common:
        if c.exists():
            return c

    raise FileNotFoundError("Could not guess SQLite path. Pass it with --db")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({name})").fetchall()]


def build_sql(conn: sqlite3.Connection, include_null_minutes: bool, order: str) -> tuple[str, list[str]]:
    stats_table = "game_player_stats"
    if not _table_exists(conn, stats_table):
        raise RuntimeError(f"Table not found: {stats_table}")

    gps_cols = set(_table_columns(conn, stats_table))

    players_table = "players" if _table_exists(conn, "players") else None
    players_cols = set(_table_columns(conn, players_table)) if players_table else set()

    team_table = None
    for candidate in ("real_teams", "teams"):
        if _table_exists(conn, candidate):
            team_table = candidate
            break
    team_cols = set(_table_columns(conn, team_table)) if team_table else set()

    # detect FK and PK
    player_team_fk = None
    if players_table and team_table:
        if "team_id" in players_cols:
            player_team_fk = "team_id"
        elif "real_team_id" in players_cols:
            player_team_fk = "real_team_id"

    team_pk = None
    if team_table:
        if "id" in team_cols:
            team_pk = "id"
        elif "team_id" in team_cols:
            team_pk = "team_id"

    # base columns we want from gps (only keep those that exist)
    wanted_gps = [
        "season_id",
        "acb_game_id",
        "acb_player_id",
        "play_time",
        "minutes_seconds",
        "plus_minus",
        "is_started",
        "created_at",
        "updated_at",
    ]
    present_gps = [c for c in wanted_gps if c in gps_cols]

    # build SELECT list + output header list (same order)
    select_cols: list[str] = []
    header: list[str] = []

    # gps base
    for c in present_gps:
        select_cols.append(f"gps.{c}")
        header.append(c)

    # Insert player/team name right after ids for nicer TSV
    # We'll rebuild to place names where we want:
    # season_id, acb_game_id, acb_player_id, player_name, team_name, ...
    def _idx(col: str) -> int:
        return header.index(col) if col in header else -1

    # We'll create a final select/header ordering explicitly
    final_select: list[str] = []
    final_header: list[str] = []

    # Always include these three first if present
    for c in ("season_id", "acb_game_id", "acb_player_id"):
        if c in header:
            final_select.append(f"gps.{c}")
            final_header.append(c)

    # player_name/team_name via joins (or NULL)
    if players_table and "name" in players_cols:
        final_select.append("p.name AS player_name")
    else:
        final_select.append("NULL AS player_name")
    final_header.append("player_name")

    if team_table and player_team_fk and team_pk and "name" in team_cols:
        final_select.append("t.name AS team_name")
    else:
        final_select.append("NULL AS team_name")
    final_header.append("team_name")

    # then the rest of gps columns (excluding the three we already put first)
    for c in header:
        if c in ("season_id", "acb_game_id", "acb_player_id"):
            continue
        final_select.append(f"gps.{c}")
        final_header.append(c)

    from_sql = f"FROM {stats_table} gps"
    join_sql = ""
    if players_table:
        join_sql += f"""
LEFT JOIN {players_table} p
  ON p.acb_player_id = gps.acb_player_id
 AND (p.season_id = gps.season_id OR p.season_id = substr(gps.season_id, 1, 4))
""".rstrip()
        if team_table and player_team_fk and team_pk:
            join_sql += f"""
LEFT JOIN {team_table} t
  ON t.{team_pk} = p.{player_team_fk}
""".rstrip()

    where = []
    if not include_null_minutes and "minutes_seconds" in gps_cols:
        where.append("gps.minutes_seconds IS NOT NULL")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # order: only use columns that exist
    if order == "game_player":
        order_parts = ["gps.season_id", "gps.acb_game_id"]
        if "is_started" in gps_cols:
            order_parts.append("gps.is_started DESC")
        if "minutes_seconds" in gps_cols:
            order_parts.append("gps.minutes_seconds DESC")
        order_parts.append("gps.acb_player_id")
        order_sql = "ORDER BY " + ", ".join(order_parts)
    elif order == "player_game":
        order_sql = "ORDER BY gps.season_id, gps.acb_player_id, gps.acb_game_id"
    else:
        if "updated_at" in gps_cols:
            order_sql = "ORDER BY gps.updated_at DESC"
        else:
            order_sql = "ORDER BY gps.acb_game_id DESC"

    sql = f"""
SELECT
  {", ".join(final_select)}
{from_sql}
{join_sql}
{where_sql}
{order_sql}
"""
    return sql, final_header


def main() -> None:
    ap = argparse.ArgumentParser(description="Export game_player_stats to TSV (with player/team names when possible).")
    ap.add_argument("--db", type=str, default=None, help="Path to SQLite file")
    ap.add_argument("--out", type=str, default="game_player_stats.tsv", help="Output TSV path")
    ap.add_argument("--season", type=str, default=None, help="Filter season_id (e.g. 2025-26)")
    ap.add_argument("--game", type=str, default=None, help="Filter acb_game_id (e.g. 104459)")
    ap.add_argument("--player", type=str, default=None, help="Filter acb_player_id")
    ap.add_argument("--include-null-minutes", action="store_true", help="Include DNP rows (minutes_seconds is NULL)")
    ap.add_argument("--order", type=str, default="game_player",
                    choices=["game_player", "player_game", "updated_desc"],
                    help="Sort order")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else guess_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    sql, header = build_sql(conn, include_null_minutes=args.include_null_minutes, order=args.order)

    # Add filters on gps.*
    where_extra = []
    params: dict[str, object] = {}

    if args.season:
        where_extra.append("gps.season_id = :season_id")
        params["season_id"] = args.season.strip()

    if args.game:
        where_extra.append("gps.acb_game_id = :acb_game_id")
        params["acb_game_id"] = args.game.strip()

    if args.player:
        where_extra.append("gps.acb_player_id = :acb_player_id")
        params["acb_player_id"] = args.player.strip()

    if where_extra:
        if "WHERE" in sql:
            sql = sql.replace("\nORDER BY", "\nAND " + " AND ".join(where_extra) + "\nORDER BY")
        else:
            sql = sql.replace("\nORDER BY", "\nWHERE " + " AND ".join(where_extra) + "\nORDER BY")

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        for r in rows:
            w.writerow([r[h] if h in r.keys() else None for h in header])

    print(f"OK: wrote {len(rows)} rows to {out_path.resolve()}")


if __name__ == "__main__":
    main()