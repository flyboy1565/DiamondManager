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
    return {
        "id": str(game.id),
        "home_score": game.home_score,
        "away_score": game.away_score,
        "is_live": game.is_live,
        "current_inning": game.current_inning,
        "is_top_inning": game.is_top_inning,
        "outs": game.outs,
        "balls": game.balls,
        "strikes": game.strikes,
        "pitch_count": game.pitch_count,
        "is_completed": game.is_completed,
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
        "scoring_data": game.scoring_data,
    }
