from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_db, require_admin
from app.core.roles import ALL_ROLES
from app.models.user import User

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

@router.get("/users")
def list_users(admin=Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.user_id.asc()).all()
    return [
        {
            "user_id": u.user_id,
            "email": u.email,
            "username": u.username,
            "team_name": u.team_name,
            "role": u.role,
        }
        for u in users
    ]

@router.post("/users/{user_id}/role")
def set_role(user_id: int, payload: dict, admin=Depends(require_admin), db: Session = Depends(get_db)):
    role = (payload.get("role") or "").strip().lower()
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {sorted(ALL_ROLES)}")

    u = db.query(User).filter_by(user_id=user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.role = role
    db.commit()
    return {"ok": True, "user_id": u.user_id, "role": u.role}
