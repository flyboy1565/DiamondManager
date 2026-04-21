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

class GameLiveUpdateSchema(Schema):
    # Score
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    
    # Baseball-specific state
    current_inning: Optional[int] = None
    is_top_inning: Optional[bool] = None
    outs: Optional[int] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    
    # Status
    is_live: Optional[bool] = True
    is_completed: Optional[bool] = False    

class GameCreateSchema(Schema):
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    date_time: datetime
    location: str