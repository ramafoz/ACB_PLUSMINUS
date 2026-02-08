from pydantic import BaseModel

class CaptainRequest(BaseModel):
    player_id: str

class InitTeamRequest(BaseModel):
    player_ids: list[str]

class PlayerIdRequest(BaseModel):
    player_id: str

class InitTeamRequest(BaseModel):
    player_ids: list[str]
