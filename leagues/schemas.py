from ninja import Schema
from uuid import UUID
from typing import List, Optional

# ==============================================================================
# ORGANIZATION SCHEMAS
# ==============================================================================

class OrganizationSchema(Schema):
    id: UUID
    name: str
    city: str
    state: str
    zip_code: str

class OrganizationCreateSchema(Schema):
    name: str
    city: str
    state: str
    zip_code: str

class OrganizationUpdateSchema(Schema):
    name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


# ==============================================================================
# SEASON SCHEMAS
# ==============================================================================

class SeasonSchema(Schema):
    id: UUID
    organization_id: UUID
    season: str  # e.g., 'Spring', 'Fall'
    year: int
    is_active: bool
    name: str    # Corresponds to the model's computed @property (e.g., 'Spring-2026')
    detail_url: str

class SeasonCreateSchema(Schema):
    organization_id: UUID
    season: str
    year: int

class SeasonUpdateSchema(Schema):
    season: Optional[str] = None
    year: Optional[int] = None
    is_active: Optional[bool] = None


# ==============================================================================
# DIVISION SCHEMAS (New Structural Layer)
# ==============================================================================

class DivisionSchema(Schema):
    id: int
    season_id: UUID
    name: str     # e.g., '10U', '12U', 'Majors'
    preset_type: str
    notes: Optional[str] = None
    allowed_positions: list[str] = []

class DivisionCreateSchema(Schema):
    season_id: UUID
    name: str
    preset_type: Optional[str] = 'CUSTOM'
    notes: Optional[str] = None
    allowed_positions: Optional[list[str]] = None

class DivisionUpdateSchema(Schema):
    name: Optional[str] = None
    preset_type: Optional[str] = None
    notes: Optional[str] = None
    allowed_positions: Optional[list[str]] = None

class DivisionPositionUpdateSchema(Schema):
    positions: list[str]

class CloneDivisionsSchema(Schema):
    source_season_id: UUID
    target_season_id: UUID


# ==============================================================================
# TEAM SCHEMAS
# ==============================================================================

class TeamSchema(Schema):
    id: UUID
    division_id: int  # Pivoted from season_id to map to the new database layer
    name: str
    color: Optional[str] = None
    access_code: str   # Exposed so clients/apps can handle team fan connections
    team_detail_url: str

class TeamCreateSchema(Schema):
    division_id: int
    name: str
    color: Optional[str] = "White"

class TeamUpdateSchema(Schema):
    name: Optional[str] = None
    color: Optional[str] = None


# ==============================================================================
# ORG-WIDE ADMIN SCHEMAS
# ==============================================================================

class OrgTeamSchema(Schema):
    id: UUID
    name: str
    color: Optional[str] = None
    access_code: str
    division_name: str
    division_id: int
    season_name: str
    season_id: UUID
    player_count: int
    coach_count: int


class OrgPlayerSchema(Schema):
    id: int
    first_name: str
    last_name: str
    jersey_number: Optional[str] = None
    team_name: str
    team_id: UUID
    division_name: str
    season_name: str


class OrgVolunteerSchema(Schema):
    user_id: int
    username: str
    email: str
    first_name: str
    last_name: str
    role: str
    team_name: str
    team_id: UUID
    division_name: str
    season_name: str


# ==============================================================================
# ALERT SCHEMAS
# ==============================================================================

class AlertSchema(Schema):
    id: UUID
    organization_id: Optional[UUID] = None
    division_id: Optional[int] = None
    team_id: Optional[UUID] = None
    title: str
    message: str
    created_by_username: str = ""
    created_at: str = ""

class AlertCreateSchema(Schema):
    organization_id: UUID
    division_id: Optional[int] = None
    team_id: Optional[UUID] = None
    title: str
    message: str