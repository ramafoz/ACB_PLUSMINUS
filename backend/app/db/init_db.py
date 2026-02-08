from app.db.session import engine
from app.db.base import Base

# IMPORTANTE: esto "registra" los modelos antes de crear tablas
import app.models  # noqa: F401


def init_db():
    Base.metadata.create_all(bind=engine)
