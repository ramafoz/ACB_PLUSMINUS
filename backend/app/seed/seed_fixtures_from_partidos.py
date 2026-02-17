# app/seed/seed_fixtures_from_partidos.py
import argparse

from app.db.session import SessionLocal
from app.crud.crud_fixture import upsert_fixtures
from app.scrapers.acb_partidos import scrape_partidos, ParsedFixture
from app.services.fixture_flags import compute_flags_for_season

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-id", required=True)
    ap.add_argument("--competicion", required=True, type=int)
    ap.add_argument("--start-jornada-id", required=True, type=int)
    ap.add_argument("--rounds", required=True, type=int)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        total_created = total_updated = total_parsed = 0

        all_rows = []   # will store (round, home, away, kickoff_at)
        all_mapped = [] # objects for upsert

        for i in range(args.rounds):
            round_number = i + 1
            jornada_id = args.start_jornada_id + i

            parsed = scrape_partidos(
                season_id=args.season_id,
                competicion=args.competicion,
                jornada_id=jornada_id,
            )

            if not parsed:
                print(f"WARNING: no parsed fixtures for round {round_number} (jornada_id={jornada_id})")
                continue

            for fx in parsed:
                all_rows.append((round_number, fx.home_team_id, fx.away_team_id, fx.kickoff_at))

                all_mapped.append(
                    type("Tmp", (), {
                        "round_number": round_number,
                        "home_team_id": fx.home_team_id,
                        "away_team_id": fx.away_team_id,
                        "kickoff_at": fx.kickoff_at,
                        "is_finished": fx.is_finished,
                        "home_score": fx.home_score,
                        "away_score": fx.away_score,
                        "is_postponed": False,  # set later
                        "is_advanced": False,   # set later
                    })()
                )

            # compute flags
            flags = compute_flags_for_season(all_rows)

            # inject flags
            for obj in all_mapped:
                key = (obj.round_number, obj.home_team_id, obj.away_team_id)
                obj.is_postponed, obj.is_advanced = flags.get(key, (False, False))

            result = upsert_fixtures(db, season_id=args.season_id, parsed=all_mapped)
            total_created += result["created"]
            total_updated += result["updated"]
            total_parsed += result["total"]

            print(f"Round {round_number} jornada_id={jornada_id}: {result}")

        print({"created": total_created, "updated": total_updated, "total": total_parsed})

    finally:
        db.close()

if __name__ == "__main__":
    main()
