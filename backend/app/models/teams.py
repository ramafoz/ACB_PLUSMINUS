from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint, Index

from app.db.base import Base  # ajusta si tu Base está en otro sitio
from app.core.game_config import SEASON_ID  # si lo tienes así; si no, no lo uses aquí


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)

    season_id = Column(String, index=True, nullable=False)
    team_id = Column(String, nullable=False)         # ej: "BAR", "RMB"
    acb_club_id = Column(String, nullable=True, index=True)  # ej "14"
    name = Column(String, nullable=False)            # ej: "FC Barcelona"
    short_name = Column(String, nullable=True)       # ej: "Barça"
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("season_id", "team_id", name="uq_team_season_teamid"),
        Index("ix_team_season_active", "season_id", "is_active"),
    )
