from typing import Optional, List
from ninja import Schema
from pydantic import UUID4
from datetime import datetime, date


class StreamStartResponseSchema(Schema):
    srt_url: str
    srt_stream_id: str
    full_srt_url: str
    youtube_video_id: str = ""
    youtube_broadcast_id: str = ""
    youtube_stream_id: str = ""
    embed_url: str = ""
    stream_status: str = ""

# Original schemas from HEAD (full set)
class TeamEventSchema(Schema):
    id: UUID4
    scope: str
    organization_id: Optional[UUID4] = None
    division_id: Optional[int] = None
    team_id: Optional[UUID4] = None
    counts_against_limit: bool
    event_type: str
    title: str
    description: Optional[str] = None
    date_time: datetime
    location: Optional[str] = None
    game_id: Optional[UUID4] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    status: str
    opponent_team_id: Optional[UUID4] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    is_home_game: Optional[bool] = None
    is_live: bool
    current_inning: Optional[int] = None
    is_top_inning: bool
    outs: Optional[int] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    pitch_count: Optional[int] = None
    practice_focus: Optional[str] = None
    attendance_required: bool
    tournament_name: Optional[str] = None
    tournament_division: Optional[str] = None

class TeamEventCreateSchema(Schema):
    scope: str = "TEAM"
    organization_id: Optional[UUID4] = None
    division_id: Optional[int] = None
    team_id: Optional[UUID4] = None
    counts_against_limit: bool = True
    event_type: str
    title: str
    description: Optional[str] = None
    date_time: datetime
    location: Optional[str] = None
    opponent_team_id: Optional[UUID4] = None
    is_home_game: Optional[bool] = None
    practice_focus: Optional[str] = None
    attendance_required: bool = False
    tournament_name: Optional[str] = None
    tournament_division: Optional[str] = None

class TeamEventUpdateSchema(Schema):
    event_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    date_time: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    opponent_team_id: Optional[UUID4] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    is_home_game: Optional[bool] = None
    is_live: Optional[bool] = None
    current_inning: Optional[int] = None
    is_top_inning: Optional[bool] = None
    outs: Optional[int] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    pitch_count: Optional[int] = None
    practice_focus: Optional[str] = None
    attendance_required: Optional[bool] = None
    tournament_name: Optional[str] = None
    tournament_division: Optional[str] = None
    counts_against_limit: Optional[bool] = None
    away_score: Optional[int] = None

# --- Game Schemas ---
class GameSchema(Schema):
    id: UUID4
    season_id: UUID4
    home_team_id: UUID4
    away_team_id: UUID4
    home_team_name: str = ""
    away_team_name: str = ""
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
    stream_status: Optional[str] = None
    youtube_video_id: Optional[str] = None

class LineupEntrySchema(Schema):
    id: int
    team_id: UUID4
    team_name: str
    player_id: int
    player_name: str
    batting_order: int
    position: str | None = None
    is_active: bool
    division_id: int | None = None

class LineupEntryCreateSchema(Schema):
    team_id: UUID4
    player_id: int
    batting_order: int
    position: Optional[str] = None

# --- Scheduling Schemas ---

class TeamEventSchema(Schema):
    id: UUID4
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
    opponent_team_id: Optional[UUID4] = None
    opponent_team_name: Optional[str] = None
    team_id: Optional[UUID4] = None
    team_name: Optional[str] = None
    division_id: Optional[int] = None
    division_name: Optional[str] = None
    game_id: Optional[UUID4] = None

class TeamEventCreateSchema(Schema):
    event_type: str
    title: str
    description: Optional[str] = None
    date_time: datetime
    location: str = ""
    opponent_team_id: Optional[UUID4] = None
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
    opponent_team_id: Optional[UUID4] = None
    is_home_game: Optional[bool] = None
    counts_against_limit: Optional[bool] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    practice_focus: Optional[str] = None
    attendance_required: Optional[bool] = None

class WeeklyTeamStatusSchema(Schema):
    team_id: UUID4
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
    home_team_id: UUID4
    away_team_id: UUID4
    event_type: str = "TEAM_GAME"
    date_time: datetime
    location: str = ""
    counts_against_limit: bool = True

class LocationConflictSchema(Schema):
    id: UUID4
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
    id: UUID4
    season_id: UUID4
    home_team_id: UUID4
    away_team_id: UUID4
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

class SetBatterSchema(Schema):
    side: str
    player_id: Optional[int] = None
    skip: bool = False

class RecordPitchSchema(Schema):
    type: str
    extra: Optional[dict] = None

class NonPitchSchema(Schema):
    type: str

class SetPitcherSchema(Schema):
    player_id: int

class BatterSchema(Schema):
    player_id: int

class ScoreUpdateSchema(Schema):
    home_score: int
    away_score: int

class ScoringTokenSchema(Schema):
    token: str
    expires_at: datetime
    is_active: bool

class ScoreboardSchema(Schema):
    game: GameSchema
    home_lineup: List[LineupEntrySchema]
    away_lineup: List[LineupEntrySchema]

class GameScoreDetailSchema(Schema):
    id: UUID4
    home_team_name: str
    away_team_name: str
    home_score: int
    away_score: int
    current_inning: int
    is_top_inning: bool
    outs: int
    balls: int
    strikes: int
    pitch_count: int
    is_live: bool
    is_completed: bool
    scoring_data: Optional[dict] = None
    date_time: datetime
    location: str
    stream_status: Optional[str] = None
    youtube_video_id: Optional[str] = None
class OrganizationSettingsSchema(Schema):
    max_events_per_team_per_week: int
class EndGameSchema(Schema):
    final_home_score: Optional[int] = None
    final_away_score: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
class GameLiveUpdateSchema(Schema):
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    current_inning: Optional[int] = None
    is_top_inning: Optional[bool] = None
    outs: Optional[int] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    is_live: Optional[bool] = True
    is_completed: Optional[bool] = False
class RuleSchema(Schema):
    title: str
    description: str
    category: str

class OrganizationYouTubeConfigSchema(Schema):
    youtube_channel_id: Optional[str] = ""
    youtube_client_id: Optional[str] = ""
    youtube_client_secret: Optional[str] = ""
    youtube_refresh_token: Optional[str] = ""
    streaming_server_srt_url: Optional[str] = ""
    privacy_status: Optional[str] = "unlisted"
    is_enabled: bool = False


class YouTubeOAuthStartSchema(Schema):
    authorize_url: str
    redirect_uri: str


class YouTubeOAuthCallbackSchema(Schema):
    connected: bool
    organization_id: str
    youtube_channel_id: str = ""
