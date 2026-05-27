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
    id: UUID
    season_id: UUID
    name: str     # e.g., '10U', '12U', 'Majors'
    preset_type: str
    notes: Optional[str] = None

class DivisionCreateSchema(Schema):
    season_id: UUID
    name: str
    preset_type: Optional[str] = 'CUSTOM'
    notes: Optional[str] = None

class DivisionUpdateSchema(Schema):
    name: Optional[str] = None
    preset_type: Optional[str] = None
    notes: Optional[str] = None

class CloneDivisionsSchema(Schema):
    source_season_id: UUID
    target_season_id: UUID


# ==============================================================================
# TEAM SCHEMAS
# ==============================================================================

class TeamSchema(Schema):
    id: UUID
    division_id: UUID  # Pivoted from season_id to map to the new database layer
    name: str
    color: Optional[str] = None
    access_code: str   # Exposed so clients/apps can handle team fan connections
    team_detail_url: str

class TeamCreateSchema(Schema):
    division_id: UUID
    name: str
    color: Optional[str] = "White"

class TeamUpdateSchema(Schema):
    name: Optional[str] = None
    color: Optional[str] = None