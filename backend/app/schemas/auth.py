from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)
    team_name: str = Field(min_length=2, max_length=60)
    username: str = Field(min_length=3, max_length=20)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
