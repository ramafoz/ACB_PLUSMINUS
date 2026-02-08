from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Para SQLite hace falta este argumento si vas a usarlo con FastAPI (varios hilos)
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# Dependencia para FastAPI: te da una sesión de BD y la cierra al final
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
