from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest
from app.core.security import verify_password, create_access_token
from app.core.roles import ROLE_USER


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    # ¿Ya existe ese email? ¿Y ese usuario?
    if db.query(User).filter_by(email=data.email.lower().strip()).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if db.query(User).filter_by(username=data.username.strip()).first():
        raise HTTPException(status_code=400, detail="Username already in use")

    user = User(
        email=data.email.lower().strip(),
        password_hash=hash_password(data.password),
        team_name=data.team_name.strip(),
        username=data.username.strip(),
        role=ROLE_USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"ok": True, "user_id": user.user_id}

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        {
            "sub": str(user.user_id),
            "is_admin": user.is_admin,
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }
