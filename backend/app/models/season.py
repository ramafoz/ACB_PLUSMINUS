from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from app.db.base import Base


class SeasonState(Base):
    __tablename__ = "season_state"

    season_id = Column(String, primary_key=True)  # 1 fila por temporada
    is_preseason = Column(Boolean, nullable=False, default=True)

    current_round = Column(Integer, nullable=True)        # jornada activa (opcional)
    last_committed_round = Column(Integer, nullable=True) # última jornada commiteada

    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
