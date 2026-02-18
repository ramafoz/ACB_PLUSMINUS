from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class FixtureCreate(BaseModel):
    round_number: int
    home_team_id: str
    away_team_id: str
    kickoff_at: Optional[datetime] = None
    is_postponed: bool = False
    is_advanced: bool = False
    season_id: str
    acb_game_id: str | None = None
    live_url: str | None = None


class FixtureUpdate(BaseModel):
    kickoff_at: Optional[datetime] = None
    is_postponed: Optional[bool] = None
    is_advanced: Optional[bool] = None
    is_finished: Optional[bool] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    season_id: Optional[str] = None
    acb_game_id: str | None = None
    live_url: str | None = None


class FixtureOut(BaseModel):
    id: int
    season_id: str
    round_number: int
    home_team_id: str
    away_team_id: str
    kickoff_at: Optional[datetime] = None
    is_postponed: bool
    is_advanced: bool
    is_finished: bool
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    acb_game_id: str | None
    live_url: str | None

    model_config = {"from_attributes": True}
