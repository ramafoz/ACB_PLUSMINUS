from pydantic import BaseModel, Field


class TeamOut(BaseModel):
    season_id: str
    team_id: str
    name: str
    short_name: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class TeamCreate(BaseModel):
    team_id: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=2, max_length=80)
    short_name: str | None = Field(default=None, max_length=40)
    is_active: bool = True


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    short_name: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None
