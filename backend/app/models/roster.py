from sqlalchemy import Column, Integer, String, UniqueConstraint
from app.db.base import Base
from datetime import datetime
from sqlalchemy import DateTime


class UserSeasonState(Base):
    __tablename__ = "user_season_state"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    season_id = Column(String, index=True, nullable=False)

    budget_base = Column(Integer, nullable=False)
    budget_current = Column(Integer, nullable=False)
    changes_used_total = Column(Integer, nullable=False, default=0)

    last_frozen_round = Column(Integer, nullable=True)

    # True hasta que arranque la competición (jornada 1 cerrada)
    is_preseason = Column(Integer, nullable=False, default=1)  # 1/0 para SQLite simple

    __table_args__ = (UniqueConstraint("user_id", "season_id", name="uq_user_season_state"),)


class UserRosterBase(Base):
    __tablename__ = "user_roster_base"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    season_id = Column(String, index=True, nullable=False)
    player_id = Column(String, index=True, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "season_id", "player_id", name="uq_roster_base"),)


class UserRosterDraft(Base):
    __tablename__ = "user_roster_draft"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    season_id = Column(String, index=True, nullable=False)
    player_id = Column(String, index=True, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "season_id", "player_id", name="uq_roster_draft"),)


class UserCaptain(Base):
    __tablename__ = "user_captain"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    season_id = Column(String, index=True, nullable=False)
    captain_player_id = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "season_id", name="uq_user_captain"),)


class UserDraftAction(Base):
    __tablename__ = "user_draft_actions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    season_id = Column(String, index=True, nullable=False)

    action = Column(String, nullable=False)  # "ADD" o "REMOVE"
    player_id = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
