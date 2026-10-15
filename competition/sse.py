import json
import threading
from queue import Queue, Empty
from typing import Dict, List, Optional

_subscribers: Dict[str, List[Queue]] = {}
_lock = threading.Lock()


def subscribe(game_id: str) -> Queue:
    with _lock:
        if game_id not in _subscribers:
            _subscribers[game_id] = []
        q: Queue = Queue()
        _subscribers[game_id].append(q)
        return q


def unsubscribe(game_id: str, queue: Queue):
    with _lock:
        if game_id in _subscribers:
            _subscribers[game_id] = [q for q in _subscribers[game_id] if q is not queue]
            if not _subscribers[game_id]:
                del _subscribers[game_id]


def publish(game_id: str, event: str, data: dict):
    with _lock:
        for q in _subscribers.get(game_id, []):
            q.put((event, data))


def game_to_sse_data(game):
    """Full game payload pushed to SSE subscribers.

    Matches the Android ``GameData`` model (all required fields present) so the
    client can decode each event directly.
    """
    return {
        "id": str(game.id),
        "season_id": str(game.season_id),
        "home_team_id": str(game.home_team_id),
        "away_team_id": str(game.away_team_id),
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
        "date_time": game.date_time,
        "location": game.location,
        "home_score": game.home_score or 0,
        "away_score": game.away_score or 0,
        "is_live": game.is_live,
        "current_inning": game.current_inning or 1,
        "is_top_inning": game.is_top_inning,
        "outs": game.outs or 0,
        "balls": game.balls or 0,
        "strikes": game.strikes or 0,
        "pitch_count": game.pitch_count or 0,
        "is_completed": game.is_completed,
        "scoring_data": game.scoring_data,
        "stream_status": game.stream_status,
        "youtube_video_id": game.youtube_video_id,
    }
