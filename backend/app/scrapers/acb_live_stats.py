from __future__ import annotations

import json
import re
from typing import Any
import httpx

LIVE_STATS_URL = "https://live.acb.com/es/partidos/{game_id}/estadisticas"

def _mmss_to_seconds(mmss: str | None) -> int | None:
    if not mmss:
        return None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", mmss)
    if not m:
        return None
    minutes = int(m.group(1))
    seconds = int(m.group(2))
    return minutes * 60 + seconds

def fetch_live_stats_html(game_id: str, timeout: float = 20.0) -> str:
    url = LIVE_STATS_URL.format(game_id=game_id)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text

def parse_minutes_plusminus(html: str) -> list[dict]:
    out: list[dict] = []
    decoder = json.JSONDecoder()

    # Iterate through each JSON object that starts with {"player":
    start = 0
    while True:
        i = html.find('{"player":', start)
        if i == -1:
            break
        try:
            obj, end = decoder.raw_decode(html, i)
        except Exception:
            start = i + 9
            continue

        # expected shape from your sample:
        # {"player":{"id":...}, "playTime":"22:40", "plusMinus":15, "isStarted":true, ...}
        try:
            player = obj.get("player") or {}
            acb_player_id = str(player.get("id")) if player.get("id") is not None else None
            play_time = obj.get("playTime")
            plus_minus = obj.get("plusMinus")
            is_started = obj.get("isStarted", None)
        except Exception:
            start = end
            continue

        if acb_player_id and (play_time is not None or plus_minus is not None):
            out.append({
                "acb_player_id": acb_player_id,
                "play_time": play_time,
                "minutes_seconds": _mmss_to_seconds(play_time),
                "plus_minus": int(plus_minus) if plus_minus is not None else None,
                "is_started": bool(is_started) if is_started is not None else None,
            })

        start = end

    # Deduplicate by player id (keep last)
    uniq = {}
    for row in out:
        uniq[row["acb_player_id"]] = row
    return list(uniq.values())
