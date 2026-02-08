from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
    "user_id": user.user_id,
    "username": user.username,
    "team_name": user.team_name,
    "role": user.role,
    }
