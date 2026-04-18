from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional

class GameSchema(Schema):
    id: UUID
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    home_team_name: str 
    away_team_name: str
    date_time: datetime
    location: str
    home_score: int
    away_score: int
    is_completed: bool

class GameCreateSchema(Schema):
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    date_time: datetime
    location: str