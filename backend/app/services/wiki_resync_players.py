from __future__ import annotations

from typing import Dict, List, Tuple
from sqlalchemy.orm import Session

from app.core.game_config import ACB_TEMPORADA_ID
from app.models.players import Player
from app.models.teams import Team
from app.scrapers.acb_players import fetch_team_roster_html, parse_roster_players, canonicalize_position


def resync_players_from_acb(db: Session, *, season_id: str, only_active_teams: bool = True) -> dict:
    teams_q = db.query(Team).filter(Team.season_id == season_id)
    if only_active_teams:
        teams_q = teams_q.filter(Team.is_active == True)

    teams = teams_q.all()

    created = 0
    updated = 0
    deactivated = 0
    teams_ok = 0
    teams_failed = 0

    for t in teams:
        if not t.acb_club_id:
            continue

        info = fetch_team_roster_html(
            acb_club_id=t.acb_club_id, 
            season_id=ACB_TEMPORADA_ID, 
            include_html=True)
        html = info.get("html") or ""
        if not html:
            teams_failed += 1
            continue

        scraped = parse_roster_players(html)
        teams_ok += 1

        # scraped ids for this team
        seen_ids = set()

        for sp in scraped:
            acb_player_id = (sp.get("acb_player_id") or "").strip()
            if not acb_player_id:
                # If this happens, skip (otherwise you can create NULL duplicates)
                continue

            seen_ids.add(acb_player_id)

            name = (sp.get("name") or "").strip()
            pos = canonicalize_position(sp.get("position_raw") or "")

            existing = (
                db.query(Player)
                .filter(Player.season_id == season_id, Player.acb_player_id == acb_player_id)
                .first()
            )

            if existing:
                changed = False
                # If player moved team, update team_pk_id
                if existing.team_pk_id != t.id:
                    existing.team_pk_id = t.id
                    changed = True
                if name and existing.name != name:
                    existing.name = name
                    changed = True
                if pos and existing.position != pos:
                    existing.position = pos
                    changed = True
                if existing.is_active is False:
                    existing.is_active = True
                    changed = True

                if changed:
                    updated += 1
            else:
                db.add(
                    Player(
                        season_id=season_id,
                        acb_player_id=acb_player_id,
                        name=name or f"ACB_{acb_player_id}",
                        position=pos,
                        team_pk_id=t.id,
                        is_active=True,
                    )
                )
                created += 1

        # Deactivate players that were previously in this team but are no longer in scraped roster
        if seen_ids:
            q = (
                db.query(Player)
                .filter(
                    Player.season_id == season_id,
                    Player.team_pk_id == t.id,
                    Player.acb_player_id != None,
                    Player.acb_player_id.notin_(seen_ids),
                    Player.is_active == True,
                )
            )
            deactivated += q.update({"is_active": False}, synchronize_session=False)

    db.commit()
    return {
        "teams_ok": teams_ok,
        "teams_failed": teams_failed,
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
    }
