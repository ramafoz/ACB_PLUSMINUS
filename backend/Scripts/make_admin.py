from app.db.session import SessionLocal
from app.models.user import User
from app.core.roles import ROLE_ADMIN

db = SessionLocal()
u = db.query(User).filter_by(email="ramafoz@gmail.com").first()
if not u:
    print("User not found")
else:
    u.role = ROLE_ADMIN
    db.commit()
    print("OK: set admin")
db.close()
