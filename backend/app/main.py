from fastapi import FastAPI
from app.core.config import settings
from app.db.init_db import init_db
from app.api.routes.auth import router as auth_router
from app.api.routes.me import router as me_router
from app.api.routes.market import router as market_router
from app.api.routes.team import router as team_router
from app.api.routes.admin_users import router as admin_users_router
from app.api.routes.teams import router as teams_router
from app.api.routes.wiki_teams import router as wiki_teams_router
from app.api.routes.fixtures import router as fixtures_router
from app.api.routes.wiki_fixtures import router as wiki_fixtures_router

app = FastAPI(title="ACB PlusMinus")
app.include_router(me_router)
app.include_router(market_router)
app.include_router(team_router)
app.include_router(admin_users_router)
app.include_router(teams_router)
app.include_router(wiki_teams_router)
app.include_router(fixtures_router)
app.include_router(wiki_fixtures_router)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(auth_router)

@app.get("/health")
def health():
    return {"ok": True, "db": settings.DATABASE_URL}
