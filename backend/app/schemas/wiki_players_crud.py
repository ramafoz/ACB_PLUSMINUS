from typing import Optional
from pydantic import BaseModel, Field
from app.core.game_config import ACB_TEMPORADA_ID

class WikiPlayerCreate(BaseModel):
    season_id: str = Field(default=ACB_TEMPORADA_ID)
    acb_player_id: Optional[str] = None
    name: str
    position: Optional[str] = None
    team_id: str  # public id like "BAR"/"RMB" etc
    is_active: bool = True

class WikiPlayerUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[str] = None
    team_id: Optional[str] = None
    acb_player_id: Optional[str] = None
    is_active: Optional[bool] = None
