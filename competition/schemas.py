from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional, List

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

class EndGameSchema(Schema):
    home_score: Optional[int] = None
    away_score: Optional[int] = None

# --- Scheduling Schemas ---

class TeamEventSchema(Schema):
    id: UUID
    scope: str
    event_type: str
    title: str
    description: Optional[str] = None
    date_time: datetime
    location: str
    status: str
    is_home_game: Optional[bool] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    counts_against_limit: bool
    is_live: bool
    current_inning: int
    is_top_inning: bool
    outs: int
    balls: int
    strikes: int
    pitch_count: int
    opponent_team_id: Optional[UUID] = None
    opponent_team_name: Optional[str] = None
    team_id: Optional[UUID] = None
    team_name: Optional[str] = None
    division_id: Optional[int] = None
    division_name: Optional[str] = None
    game_id: Optional[UUID] = None

class TeamEventCreateSchema(Schema):
    event_type: str
    title: str
    description: Optional[str] = None
    date_time: datetime
    location: str = ""
    opponent_team_id: Optional[UUID] = None
    is_home_game: Optional[bool] = None
    counts_against_limit: bool = True
    practice_focus: Optional[str] = None
    attendance_required: bool = False

class TeamEventUpdateSchema(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    date_time: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    opponent_team_id: Optional[UUID] = None
    is_home_game: Optional[bool] = None
    counts_against_limit: Optional[bool] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    practice_focus: Optional[str] = None
    attendance_required: Optional[bool] = None

class WeeklyTeamStatusSchema(Schema):
    team_id: UUID
    team_name: str
    current_count: int
    max_allowed: int
    remaining: int

class WeeklyStatusSchema(Schema):
    week_start: str
    week_end: str
    max_allowed: int
    teams: List[WeeklyTeamStatusSchema]

class ScheduleGameSchema(Schema):
    home_team_id: UUID
    away_team_id: UUID
    event_type: str = "TEAM_GAME"
    date_time: datetime
    location: str = ""
    counts_against_limit: bool = True

class LocationConflictSchema(Schema):
    id: UUID
    team_name: str
    opponent_team_name: Optional[str] = None
    date_time: datetime
    location: str
    event_type: str
    title: str

class LocationConflictQuerySchema(Schema):
    location: str
    date: str
    division_id: int

class OrgSettingsSchema(Schema):
    max_events_per_team_per_week: int = 10

class GameScoreDetailSchema(Schema):
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
    scoring_data: Optional[dict] = None