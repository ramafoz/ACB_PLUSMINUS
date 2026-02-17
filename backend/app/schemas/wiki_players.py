from pydantic import BaseModel
from typing import List, Optional

class WikiPlayersScrapeRequest(BaseModel):
    # Explicit season for safety; we'll default later if you want.
    temporada_id: str
    # If None/empty => scrape all active teams in DB (we’ll implement in Step 4+)
    team_ids: Optional[List[str]] = None
    dry_run: bool = True
