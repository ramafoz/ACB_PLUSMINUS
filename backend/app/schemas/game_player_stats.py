from __future__ import annotations

from pydantic import BaseModel


class GamePlayerStatOut(BaseModel):
    season_id: str
    acb_game_id: str
    acb_player_id: str | None

    player_name: str | None = None
    team_id: str | None = None
    team_name: str | None = None

    play_time: str | None = None
    minutes_seconds: int | None = None
    plus_minus: int | None = None
    is_started: bool | None = None

    class Config:
        from_attributes = True


class PlayerPlusMinusAggOut(BaseModel):
    season_id: str
    acb_player_id: str

    player_name: str | None = None
    team_id: str | None = None
    team_name: str | None = None

    games: int
    minutes_seconds: int | None
    plus_minus: int | None