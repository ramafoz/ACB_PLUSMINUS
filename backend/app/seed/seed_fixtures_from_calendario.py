# app/seed/seed_fixtures_from_calendario.py
import argparse

from app.db.session import SessionLocal
from app.scrapers.acb_calendario import scrape_calendario
from app.crud.crud_fixture import upsert_fixtures

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-id", required=True, help='e.g. "2025-26"')
    ap.add_argument("--temporada", required=True, type=int, help="ACB temporada id, e.g. 90")
    args = ap.parse_args()

    parsed = scrape_calendario(temporada=args.temporada)
    if not parsed:
        raise SystemExit("No fixtures parsed from calendario (parser likely needs update).")

    db = SessionLocal()
    try:
        result = upsert_fixtures(db, season_id=args.season_id, parsed=parsed)
    finally:
        db.close()

    print({"season_id": args.season_id, "temporada": args.temporada, **result})

if __name__ == "__main__":
    main()
