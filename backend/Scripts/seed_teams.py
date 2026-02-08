from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.core.game_config import SEASON_ID
from app.models.teams import Team


def run():
    init_db()
    db = SessionLocal()

    # Si ya hay equipos de esta temporada, no duplicamos
    existing = db.query(Team).filter(Team.season_id == SEASON_ID).count()
    if existing > 0:
        print(f"Teams already seeded for season {SEASON_ID}. ({existing} rows)")
        db.close()
        return

    items = [
        Team(season_id=SEASON_ID, team_id="JOV", name="Asisa Joventut", short_name="Joventut", is_active=True),
        Team(season_id=SEASON_ID, team_id="MAN", name="Baxi Manresa", short_name="Manresa", is_active=True),
        Team(season_id=SEASON_ID, team_id="GIR", name="Bàsquet Girona", short_name="Girona", is_active=True),
        Team(season_id=SEASON_ID, team_id="ZAR", name="Casademont Zaragoza", short_name="Zaragoza", is_active=True),
        Team(season_id=SEASON_ID, team_id="GRA", name="Covirán Granada", short_name="Granada", is_active=True),
        Team(season_id=SEASON_ID, team_id="CAN", name="Dreamland Gran Canaria", short_name="Gran Canaria", is_active=True),
        Team(season_id=SEASON_ID, team_id="BAR", name="FC Barcelona", short_name="Barça", is_active=True),
        Team(season_id=SEASON_ID, team_id="LLE", name="Hiopos Lleida", short_name="Lleida", is_active=True),
        Team(season_id=SEASON_ID, team_id="BSK", name="Kosner Baskonia", short_name="Baskonia", is_active=True),
        Team(season_id=SEASON_ID, team_id="TEN", name="La Laguna Tenerife", short_name="Tenerife", is_active=True),
        Team(season_id=SEASON_ID, team_id="AND", name="Morabanc Andorra", short_name="Andorra", is_active=True),
        Team(season_id=SEASON_ID, team_id="RMA", name="Real Madrid", short_name="Real Madrid", is_active=True),
        Team(season_id=SEASON_ID, team_id="BUR", name="Recoletas Salud San Pablo Burgos", short_name="Burgos", is_active=True),
        Team(season_id=SEASON_ID, team_id="BRE", name="Río Breogán", short_name="Breo", is_active=True),
        Team(season_id=SEASON_ID, team_id="BIL", name="Surne Bilbao", short_name="Bilbao", is_active=True),
        Team(season_id=SEASON_ID, team_id="MUR", name="UCAM Murcia", short_name="Murcia", is_active=True),
        Team(season_id=SEASON_ID, team_id="UNI", name="Unicaja Málaga", short_name="Unicaja", is_active=True),
        Team(season_id=SEASON_ID, team_id="VAL", name="Valencia Basket", short_name="Valencia", is_active=True),
    ]

    db.add_all(items)
    db.commit()
    db.close()
    print(f"Seed TEAMS OK ({len(items)} teams) for season {SEASON_ID}")


if __name__ == "__main__":
    run()
