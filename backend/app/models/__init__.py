# Importa aquí los modelos para que SQLAlchemy los "vea" al crear tablas
from app.models.user import User  # noqa: F401
from app.models.market import MarketPlayerPrice  # noqa: F401
from app.models.roster import UserSeasonState, UserRosterBase, UserRosterDraft, UserCaptain, UserDraftAction  # noqa: F401
from app.models.teams import Team  # noqa: F401
from app.models.fixtures import Fixture  # noqa: F401
from app.models.season import SeasonState  # noqa: F401
