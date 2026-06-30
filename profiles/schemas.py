from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import List, Optional

class UserSchema(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str

class OrganizationLinkSchema(Schema):
    id: UUID
    name: str   

class SeasonLinkSchema(Schema):
    id: UUID
    name: str
    organization: OrganizationLinkSchema

# --- Updated to reflect Team -> Division -> Season ---
class DivisionLinkSchema(Schema):
    id: int
    name: str
    season: SeasonLinkSchema

class TeamLinkSchema(Schema):
    id: UUID
    name: str
    division: DivisionLinkSchema  # Swapped from season: SeasonLinkSchema

class TeamMembershipSchema(Schema):
    id: int
    role: str
    is_active: bool
    joined_at: datetime
    team: TeamLinkSchema

class ProfileSchema(Schema):
    user: UserSchema
    role: str
    phone_number: Optional[str] = None
    organization_id: Optional[UUID] = None

class ProfileUpdateSchema(Schema):
    role: Optional[str] = None
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


# --- Player ---
class PlayerMembershipSchema(Schema):
    team_name: str 
    jersey_number: Optional[str]
    is_active: bool

class PlayerSchema(Schema):
    id: int
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    guardian_id: int
    team_history: List[PlayerMembershipSchema]

class PlayerCreateSchema(Schema):
    team_id: UUID
    first_name: str
    last_name: str
    jersey_number: Optional[int] = None

class PlayerUpdateSchema(Schema):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    jersey_number: Optional[int] = None    

class InvitationCreateSchema(Schema):
    email: str
    team_id: UUID
    player_id: Optional[int] = None
    target_role: str = "PARENT"

class InvitationAcceptSchema(Schema):
    token: str
    username: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class JoinTeamByCodeSchema(Schema):
    access_code: str    

ProfileSchema.model_rebuild()
PlayerSchema.model_rebuild()

__all__ = [
    "UserSchema", 
    "ProfileSchema", 
    "ProfileUpdateSchema",
    "TeamMembershipSchema",
    "PlayerMembershipSchema",
    "PlayerSchema",
    "PlayerCreateSchema",
    "PlayerUpdateSchema"
]