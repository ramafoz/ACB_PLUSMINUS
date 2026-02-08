from pydantic import BaseModel

class MarketPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    team_id: str
    team_name: str
    price: int
