from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.models.market import MarketPlayerPrice

def run():
    init_db()
    db = SessionLocal()

    # Si ya hay datos, no duplicamos
    if db.query(MarketPlayerPrice).count() > 0:
        print("Market already seeded.")
        return

    items = [
        MarketPlayerPrice(season_id="2025-26", player_id="P001", name="Jugador 1",  position="BASE",  team_id="BRE", team_name="Team A", price_current=50000),
        MarketPlayerPrice(season_id="2025-26", player_id="P002", name="Jugador 2",  position="BASE",  team_id="BRE", team_name="Team A", price_current=520000),
        MarketPlayerPrice(season_id="2025-26", player_id="P003", name="Jugador 3",  position="BASE",  team_id="RMA", team_name="Team B", price_current=480000),
        MarketPlayerPrice(season_id="2025-26", player_id="P004", name="Jugador 4",  position="ALERO", team_id="RMA", team_name="Team B", price_current=161000),
        MarketPlayerPrice(season_id="2025-26", player_id="P005", name="Jugador 5",  position="ALERO", team_id="FCB", team_name="Team C", price_current=63000),
        MarketPlayerPrice(season_id="2025-26", player_id="P006", name="Jugador 6",  position="ALERO", team_id="FCB", team_name="Team C", price_current=590000),
        MarketPlayerPrice(season_id="2025-26", player_id="P007", name="Jugador 7",  position="PIVOT", team_id="MAN", team_name="Team D", price_current=300000),
        MarketPlayerPrice(season_id="2025-26", player_id="P008", name="Jugador 8",  position="PIVOT", team_id="TEN", team_name="Team D", price_current=680000),
        MarketPlayerPrice(season_id="2025-26", player_id="P009", name="Jugador 9",  position="PIVOT", team_id="GCA", team_name="Team E", price_current=320000),
        MarketPlayerPrice(season_id="2025-26", player_id="P010", name="Jugador 10", position="ALERO", team_id="MAN", team_name="Team E", price_current=260000),
        MarketPlayerPrice(season_id="2025-26", player_id="P011", name="Jugador 11", position="BASE",  team_id="TEN", team_name="Team F", price_current=450000),
        MarketPlayerPrice(season_id="2025-26", player_id="P012", name="Jugador 12", position="PIVOT", team_id="GCA", team_name="Team F", price_current=540000),
        MarketPlayerPrice(season_id="2025-26", player_id="P013", name="Jugador 10", position="PIVOT", team_id="GIR", team_name="Team E", price_current=260000),
        MarketPlayerPrice(season_id="2025-26", player_id="P014", name="Jugador 10", position="PIVOT", team_id="BSK", team_name="Team E", price_current=260000),
        MarketPlayerPrice(season_id="2025-26", player_id="P015", name="Jugador 10", position="PIVOT", team_id="GIR", team_name="Team E", price_current=260000),
        MarketPlayerPrice(season_id="2025-26", player_id="P016", name="Jugador 10", position="PIVOT", team_id="BSK", team_name="Team E", price_current=260000),
        MarketPlayerPrice(season_id="2025-26", player_id="P017", name="Jugador 10", position="PIVOT", team_id="BRE", team_name="Team E", price_current=260000),
        MarketPlayerPrice(season_id="2025-26", player_id="P018", name="Jugador 10", position="PIVOT", team_id="BRE", team_name="Team E", price_current=260000),
    ]

    db.add_all(items)
    db.commit()
    db.close()
    print("Seed OK")

if __name__ == "__main__":
    run()
