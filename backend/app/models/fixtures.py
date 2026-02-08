from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from app.db.base import Base


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True)

    season_id = Column(String, nullable=False, index=True)
    round_number = Column(Integer, nullable=False, index=True)  # jornada

    home_team_id = Column(String, ForeignKey("teams.team_id"), nullable=False)
    away_team_id = Column(String, ForeignKey("teams.team_id"), nullable=False)

    kickoff_at = Column(DateTime, nullable=True)  # puede ser NULL
    is_postponed = Column(Boolean, default=False, nullable=False)
    is_advanced = Column(Boolean, default=False, nullable=False)

    is_finished = Column(Boolean, default=False, nullable=False)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "round_number",
            "home_team_id",
            "away_team_id",
            name="uq_fixture_unique_match",
        ),
        Index("ix_fixture_season_round", "season_id", "round_number"),
    )
