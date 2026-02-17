from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship

from app.db.base import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)

    # Keep season explicit (teams are season-scoped)
    # 2025 as ID for 2025-26 season (as in ACB_TEMPORADA_ID, not SEASON_ID)
    season_id = Column(String, nullable=False, index=True) 

    # External identifier (ACB). Optional at first.
    acb_player_id = Column(String, nullable=True, index=True)

    # Display
    name = Column(String, nullable=False, index=True)

    # Proper FK to teams.id (PK)
    team_pk_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)

    # Optional metadata
    position = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    team = relationship("Team", lazy="joined")

    __table_args__ = (
        # Keep unique when we have ACB ids (but allow multiple NULLs)
        UniqueConstraint("season_id", "acb_player_id", name="uq_players_season_acb_player_id"),
        Index("ix_players_season_team_name", "season_id", "team_pk_id", "name"),
    )
