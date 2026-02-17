from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship

from app.db.base import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)

    # External identifier (ACB). Keep string: sometimes sites use non-numeric slugs/ids.
    acb_player_id = Column(String, nullable=True, index=True)

    # Display info
    name = Column(String, nullable=False, index=True)

    # Link to your existing teams table (assuming teams.team_id is a String PK or unique).
    team_id = Column(String, ForeignKey("teams.team_id"), nullable=True, index=True)

    # Optional metadata (we’ll fill later)
    position = Column(String, nullable=True)      # "G/F/C" etc (later)
    is_active = Column(Boolean, nullable=False, default=True)

    team = relationship("Team", lazy="joined")

    __table_args__ = (
        # Prevent duplicates when we do repeated scrapes:
        # If ACB id exists -> unique; if missing, we’ll fall back to (name, team_id) in code.
        UniqueConstraint("acb_player_id", name="uq_players_acb_player_id"),
        Index("ix_players_team_name", "team_id", "name"),
    )
