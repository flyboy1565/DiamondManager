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
    is_live: bool
    current_inning: int
    is_top_inning: bool
    outs: int
    balls: int
    strikes: int
    pitch_count: int
    is_completed: bool

class LineupEntrySchema(Schema):
    id: int
    team_id: UUID
    team_name: str
    player_id: int
    player_name: str
    batting_order: int
    position: str | None = None
    is_active: bool
    division_id: int | None = None

class RuleSchema(Schema):
    title: str
    description: str
    category: str

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

class SetBatterSchema(Schema):
    side: str  # "home" or "away"
    player_id: Optional[int] = None
    skip: bool = False


class RecordPitchSchema(Schema):
    type: str  # All pitch types
    extra: Optional[dict] = None  # Extra data for complex events (steal, DP, etc.)


class GameCreateSchema(Schema):
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    date_time: datetime
    location: str

class LineupEntryCreateSchema(Schema):
    team_id: UUID
    player_id: int
    batting_order: int
    position: Optional[str] = None

class LineupEntryUpdateSchema(Schema):
    batting_order: Optional[int] = None
    position: Optional[str] = None
    is_active: Optional[bool] = None

class CloneLineupSchema(Schema):
    source_game_id: UUID