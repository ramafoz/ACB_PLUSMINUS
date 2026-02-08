from datetime import datetime

from sqlalchemy import Column, Integer, String, UniqueConstraint, ForeignKey

from app.db.base import Base


class MarketPlayerPrice(Base):
    __tablename__ = "market_player_prices"

    id = Column(Integer, primary_key=True)
    season_id = Column(String, index=True, nullable=False)

    player_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)

    # NUEVO: team_id estable
    team_id = Column(String, ForeignKey("teams.team_id"), nullable=False, index=True)

    # opcional: display name (puede quedarse)
    team_name = Column(String, nullable=False)

    price_current = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("season_id", "player_id", name="uq_market_player_season_player"),
    )
