from pydantic import BaseModel, Field
from typing import Optional
from app.core.game_config import ACB_TEMPORADA_ID


class TeamOut(BaseModel):
    season_id: str
    team_id: str
    name: str
    short_name: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class TeamCreate(BaseModel):
    season_id: str = Field(default=ACB_TEMPORADA_ID)
    team_id: str
    name: str
    short_name: Optional[str] = None
    acb_club_id: Optional[str] = None
    is_active: bool = True

class TeamUpdate(BaseModel):
    season_id: Optional[str] = None  # only needed if you want to PATCH a non-default season
    name: Optional[str] = None
    short_name: Optional[str] = None
    acb_club_id: Optional[str] = None
    is_active: Optional[bool] = None
