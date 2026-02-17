from pydantic import BaseModel
from typing import Optional


class PlayerOut(BaseModel):
    id: int
    name: str
    team_id: Optional[str] = None
    acb_player_id: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True
