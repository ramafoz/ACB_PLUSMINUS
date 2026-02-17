from pydantic import BaseModel, Field
from typing import List, Optional

from app.core.game_config import ACB_TEMPORADA_ID

class WikiPlayersScrapeRequest(BaseModel):
    # Explicit season for safety; we'll default later if you want.
    temporada_id: str = Field(default=str(ACB_TEMPORADA_ID))
    # If None/empty => scrape all active teams in DB (we’ll implement in Step 4+)
    team_ids: Optional[List[str]] = None
    dry_run: bool = True
