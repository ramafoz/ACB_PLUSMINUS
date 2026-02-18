import sqlite3
import sys
from pathlib import Path

def main():
    # Usage:
    #   python scripts/sqlite_patch_fixtures.py path/to/your.sqlite
    # If no arg is provided, tries backend/app.db or backend/rus_db.sqlite etc (you can tweak defaults).
    if len(sys.argv) >= 2:
        db_path = Path(sys.argv[1]).expanduser().resolve()
    else:
        # ---- CHANGE THIS DEFAULT if your sqlite has a different name/location ----
        db_path = Path("app.db").resolve()

    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        print("Run as: python scripts/sqlite_patch_fixtures.py /full/path/to/db.sqlite")
        sys.exit(1)

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    # Check existing columns
    cur.execute("PRAGMA table_info(fixtures)")
    cols = {row[1] for row in cur.fetchall()}  # row[1] is column name

    changes = 0

    if "acb_game_id" not in cols:
        print("Adding column fixtures.acb_game_id ...")
        cur.execute("ALTER TABLE fixtures ADD COLUMN acb_game_id VARCHAR(32)")
        changes += 1
    else:
        print("OK: fixtures.acb_game_id already exists")

    if "live_url" not in cols:
        print("Adding column fixtures.live_url ...")
        cur.execute("ALTER TABLE fixtures ADD COLUMN live_url VARCHAR(512)")
        changes += 1
    else:
        print("OK: fixtures.live_url already exists")

    # Index (safe even if column already exists)
    print("Ensuring index ix_fixtures_acb_game_id ...")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_fixtures_acb_game_id ON fixtures (acb_game_id)")

    con.commit()
    con.close()

    print(f"DONE. Applied {changes} schema change(s) to: {db_path}")

if __name__ == "__main__":
    main()
