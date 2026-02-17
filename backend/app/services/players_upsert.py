from typing import List, Dict, Tuple
from sqlalchemy.orm import Session

from app.models.players import Player


def upsert_roster_players(
    db: Session,
    season_id: str,
    team_pk_id: int,
    items: List[Dict[str, str]],
) -> Tuple[int, int]:
    inserted = 0
    updated = 0

    for it in items:
        acb_player_id = (it.get("acb_player_id") or "").strip() or None
        name = (it.get("name") or "").strip()
        position = (it.get("position") or "").strip() or None

        if not name:
            continue

        q = db.query(Player).filter(Player.season_id == season_id)

        if acb_player_id:
            q = q.filter(Player.acb_player_id == acb_player_id)
        else:
            q = q.filter(Player.name == name, Player.team_pk_id == team_pk_id)

        obj = q.first()
        if obj is None:
            db.add(Player(
                season_id=season_id,
                acb_player_id=acb_player_id,
                name=name,
                position=position,
                team_pk_id=team_pk_id,
                is_active=True,
            ))
            inserted += 1
        else:
            changed = False
            if obj.name != name:
                obj.name = name
                changed = True
            if obj.position != position:
                obj.position = position
                changed = True
            if obj.team_pk_id != team_pk_id:
                obj.team_pk_id = team_pk_id
                changed = True
            if obj.is_active is not True:
                obj.is_active = True
                changed = True

            if changed:
                updated += 1

    return inserted, updated
