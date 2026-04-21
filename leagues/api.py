from typing import List
from uuid import UUID
from ninja import Router
from django.shortcuts import get_object_or_404
from django.urls import reverse

from ninja_jwt.authentication import JWTAuth

from .models import Organization, Team, Season
from . import schemas
from profiles.models import Player
import profiles.schemas as profile_schemas 

router = Router(auth=JWTAuth())


# --- ORGANIZATION ENDPOINTS ---
@router.get("/organizations", response=List[schemas.OrganizationSchema])
def list_organizations(request):
    return Organization.objects.all()

@router.post("/organizations", response={201: schemas.OrganizationSchema, 403: dict})
def create_organization(request, data: schemas.OrganizationCreateSchema):
    if request.auth.profile.role != "ORG_OWNER":
        return 403, {"message": "You do not have permission to create an organization."}
    return 201, Organization.objects.create(**data.dict())

@router.put("/organizations/{org_id}", response=schemas.OrganizationSchema)
def update_organization(request, org_id: UUID, data: schemas.OrganizationUpdateSchema):
    org = get_object_or_404(Organization, id=org_id)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(org, attr, value)
    org.save()
    return org

@router.delete("/organizations/{org_id}")
def delete_organization(request, org_id: UUID):
    get_object_or_404(Organization, id=org_id).delete()
    return {"success": True}

# --- SEASON ENDPOINTS ---
@router.get("/organizations/{org_id}/seasons", response=List[schemas.SeasonSchema])
def list_org_seasons(request, org_id: UUID):
    seasons = Season.objects.filter(organization_id=org_id)
    result = []
    for s in seasons:
        path = reverse("api-1.0.0:get_season", kwargs={"season_id": s.id})
        result.append({**s.__dict__, "detail_url": request.build_absolute_uri(path)})
    return result

@router.get("/seasons/{season_id}", response=schemas.SeasonSchema, url_name="get_season")
def get_season(request, season_id: UUID):
    season = get_object_or_404(Season, id=season_id)
    path = reverse("api-1.0.0:get_season", kwargs={"season_id": season.id})
    return {**season.__dict__, "detail_url": request.build_absolute_uri(path)}

@router.post("/seasons", response={201: schemas.SeasonSchema})
def create_season(request, data: schemas.SeasonCreateSchema):
    season = Season.objects.create(**data.dict())
    return 201, get_season(request, season.id)

# --- TEAM ENDPOINTS ---
@router.get("/seasons/{season_id}/teams", response=List[schemas.TeamSchema])
def list_teams(request, season_id: UUID):
    teams = Team.objects.filter(season_id=season_id)
    result = []
    for t in teams:
        path = reverse("api-1.0.0:get_team", kwargs={"team_id": t.id})
        result.append({**t.__dict__, "team_detail_url": request.build_absolute_uri(path)})
    return result

@router.get("/teams/{team_id}", response=schemas.TeamSchema, url_name="get_team")
def get_team(request, team_id: UUID):
    team = get_object_or_404(Team, id=team_id)
    path = reverse("api-1.0.0:get_team", kwargs={"team_id": team.id})
    return {**team.__dict__, "team_detail_url": request.build_absolute_uri(path)}

@router.post("/teams", response={201: schemas.TeamSchema})
def create_team(request, data: schemas.TeamCreateSchema):
    team = Team.objects.create(**data.dict())
    return 201, get_team(request, team.id)

@router.put("/teams/{team_id}", response=schemas.TeamSchema)
def update_team(request, team_id: UUID, data: schemas.TeamUpdateSchema):
    team = get_object_or_404(Team, id=team_id)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(team, attr, value)
    team.save()
    return get_team(request, team.id)

# --- PLAYER ENDPOINTS ---
@router.get("/teams/{team_id}/players", response=List[profile_schemas.PlayerSchema])
def list_players(request, team_id: UUID):
    return Player.objects.filter(team_id=team_id)

