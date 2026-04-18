from ninja import Schema
from uuid import UUID
from datetime import date
from typing import List, Optional

# --- Organization ---
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

# --- Season ---
class SeasonSchema(Schema):
    id: UUID
    organization_id: UUID
    name: str
    start_date: date
    end_date: date
    is_active: bool
    detail_url: str

class SeasonCreateSchema(Schema):
    organization_id: UUID
    name: str
    start_date: date
    end_date: date

class SeasonUpdateSchema(Schema):
    name: Optional[str] = None
    is_active: Optional[bool] = None

# --- Team ---
class TeamSchema(Schema):
    id: UUID
    name: str
    color: Optional[str] = None
    team_detail_url: str

class TeamCreateSchema(Schema):
    season_id: UUID
    name: str
    color: Optional[str] = "White"

class TeamUpdateSchema(Schema):
    name: Optional[str] = None
    color: Optional[str] = None

# --- Player ---
class PlayerSchema(Schema):
    id: UUID
    team_id: UUID
    first_name: str
    last_name: str
    jersey_number: Optional[int] = None

class PlayerCreateSchema(Schema):
    team_id: UUID
    first_name: str
    last_name: str
    jersey_number: Optional[int] = None

class PlayerUpdateSchema(Schema):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    jersey_number: Optional[int] = None