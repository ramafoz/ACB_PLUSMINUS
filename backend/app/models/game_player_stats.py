from sqlalchemy import Column, Integer, String, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base

class GamePlayerStat(Base):
    __tablename__ = "game_player_stats"

    id = Column(Integer, primary_key=True, index=True)

    # Use SAME season_id as fixtures: "2025-26"
    season_id = Column(String(16), nullable=False, index=True)

    # Live ACB game id, e.g. "104459"
    acb_game_id = Column(String(32), nullable=False, index=True)

    # Live ACB player id, e.g. "30003966"
    acb_player_id = Column(String(32), nullable=False, index=True)

    # store raw + parsed seconds (handy)
    play_time = Column(String(8), nullable=True)           # "22:40"
    minutes_seconds = Column(Integer, nullable=True)       # 1360

    plus_minus = Column(Integer, nullable=True)

    is_started = Column(Boolean, nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("season_id", "acb_game_id", "acb_player_id", name="uq_gps_game_player"),
    )
