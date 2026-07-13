from typing import List
from uuid import UUID
from ninja import Router
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.db import transaction
from django.db.models import Count

from ninja_jwt.authentication import JWTAuth

from .models import Organization, Division, Team, Season
from . import schemas
from profiles.models import Player, TeamMembership
import profiles.schemas as profile_schemas
from competition.models import Alert

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
        result.append({
            "id": s.id,
            "organization_id": s.organization_id,
            "season": s.season,
            "year": s.year,
            "is_active": s.is_active,
            "name": s.name,
            "detail_url": request.build_absolute_uri(path)
        })
    return result

@router.get("/seasons/{season_id}", response=schemas.SeasonSchema, url_name="get_season")
def get_season(request, season_id: UUID):
    s = get_object_or_404(Season, id=season_id)
    path = reverse("api-1.0.0:get_season", kwargs={"season_id": s.id})
    return {
        "id": s.id,
        "organization_id": s.organization_id,
        "season": s.season,
        "year": s.year,
        "is_active": s.is_active,
        "name": s.name,
        "detail_url": request.build_absolute_uri(path)
    }

@router.post("/seasons", response={201: schemas.SeasonSchema})
def create_season(request, data: schemas.SeasonCreateSchema):
    season = Season.objects.create(**data.dict())
    return 201, get_season(request, season.id)


# --- DIVISION ENDPOINTS (New structural layer) ---
@router.get("/organizations/{org_id}/divisions", response=List[schemas.DivisionSchema])
def list_org_divisions(request, org_id: UUID):
    return Division.objects.filter(season__organization_id=org_id).select_related('season')

@router.get("/seasons/{season_id}/divisions", response=List[schemas.DivisionSchema])
def list_season_divisions(request, season_id: UUID):
    return Division.objects.filter(season_id=season_id)

DEFAULT_POSITIONS = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "UTL"]

@router.post("/divisions", response={201: schemas.DivisionSchema, 403: dict})
def create_division(request, data: schemas.DivisionCreateSchema):
    if request.auth.profile.role not in ["ORG_OWNER", "ORG_ADMIN"]:
        return 403, {"message": "Insufficient permissions to manage divisions."}
    kwargs = data.dict(exclude_unset=True)
    if "allowed_positions" not in kwargs or not kwargs["allowed_positions"]:
        kwargs["allowed_positions"] = DEFAULT_POSITIONS
    division = Division.objects.create(**kwargs)
    return 201, division

@router.post("/seasons/clone-divisions", response={200: List[schemas.DivisionSchema], 403: dict, 400: dict})
def clone_divisions(request, payload: schemas.CloneDivisionsSchema):
    """Clone all divisions from an old season into a brand-new season automatically."""
    if request.auth.profile.role not in ["ORG_OWNER", "ORG_ADMIN"]:
        return 403, {"message": "Insufficient system permission layer."}
        
    source_season = get_object_or_404(Season, id=payload.source_season_id)
    target_season = get_object_or_404(Season, id=payload.target_season_id)
    
    # Safety guard: cross-pollination containment
    if source_season.organization_id != target_season.organization_id:
        return 400, {"message": "Seasons must belong to the exact same organization."}

    source_divisions = Division.objects.filter(season=source_season)
    created_divisions = []

    with transaction.atomic():
        for old_div in source_divisions:
            # Use get_or_create to keep the execution idempotent if re-fired safely
            new_div, created = Division.objects.get_or_create(
                season=target_season,
                name=old_div.name,
                defaults={"notes": old_div.notes, "preset_type": old_div.preset_type, "allowed_positions": old_div.allowed_positions}
            )
            created_divisions.append(new_div)

    return 200, created_divisions


# --- DIVISION POSITIONS ---
@router.get("/divisions/{division_id}/positions", response=List[str])
def get_division_positions(request, division_id: int):
    division = get_object_or_404(Division, id=division_id)
    return division.allowed_positions or DEFAULT_POSITIONS

@router.put("/divisions/{division_id}/positions", response={200: List[str], 403: dict})
def update_division_positions(request, division_id: int, data: schemas.DivisionPositionUpdateSchema):
    if request.auth.profile.role not in ["ORG_OWNER", "ORG_ADMIN"]:
        return 403, {"message": "Insufficient permissions."}
    division = get_object_or_404(Division, id=division_id)
    division.allowed_positions = data.positions
    division.save()
    return 200, division.allowed_positions or DEFAULT_POSITIONS

# --- TEAM ENDPOINTS ---
@router.get("/divisions/{division_id}/teams", response=List[schemas.TeamSchema])
def list_teams(request, division_id: int):
    teams = Team.objects.filter(division_id=division_id)
    result = []
    for t in teams:
        path = reverse("api-1.0.0:get_team", kwargs={"team_id": t.id})
        result.append({
            "id": t.id,
            "division_id": t.division_id,
            "name": t.name,
            "color": t.color,
            "access_code": t.access_code,
            "team_detail_url": request.build_absolute_uri(path)
        })
    return result

@router.get("/teams/{team_id}", response=schemas.TeamSchema, url_name="get_team")
def get_team(request, team_id: UUID):
    t = get_object_or_404(Team, id=team_id)
    path = reverse("api-1.0.0:get_team", kwargs={"team_id": t.id})
    return {
        "id": t.id,
        "division_id": t.division_id,
        "name": t.name,
        "color": t.color,
        "access_code": t.access_code,
        "team_detail_url": request.build_absolute_uri(path)
    }

@router.post("/teams", response={201: schemas.TeamSchema})
def create_team(request, data: schemas.TeamCreateSchema):
    import secrets
    import string
    
    # Handle random secure fan access_code assignment transparently during raw API hits
    allowed_chars = string.ascii_uppercase + string.digits
    unique_code = ''.join(secrets.choice(allowed_chars) for _ in range(6))
    while Team.objects.filter(access_code=unique_code).exists():
        unique_code = ''.join(secrets.choice(allowed_chars) for _ in range(6))
        
    team = Team.objects.create(
        division_id=data.division_id,
        name=data.name,
        color=data.color,
        access_code=unique_code
    )
    return 201, get_team(request, team.id)

@router.put("/teams/{team_id}", response=schemas.TeamSchema)
def update_team(request, team_id: UUID, data: schemas.TeamUpdateSchema):
    team = get_object_or_404(Team, id=team_id)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(team, attr, value)
    team.save()
    return get_team(request, team.id)


# --- ORG-WIDE ADMIN ENDPOINTS ---
@router.get("/organizations/{org_id}/teams", response=List[schemas.OrgTeamSchema])
def list_org_teams(request, org_id: UUID):
    teams = Team.objects.filter(
        division__season__organization_id=org_id
    ).select_related('division__season').annotate(
        player_count=Count('playermembership'),
        coach_count=Count('coaches')
    )
    return [
        {
            "id": t.id,
            "name": t.name,
            "color": t.color,
            "access_code": t.access_code,
            "division_name": t.division.name,
            "division_id": t.division_id,
            "season_name": t.division.season.name,
            "season_id": t.division.season_id,
            "player_count": t.player_count,
            "coach_count": t.coach_count,
        }
        for t in teams
    ]


@router.get("/organizations/{org_id}/players", response=List[schemas.OrgPlayerSchema])
def list_org_players(request, org_id: UUID):
    from profiles.models import PlayerMembership
    memberships = PlayerMembership.objects.filter(
        team__division__season__organization_id=org_id
    ).select_related(
        'player', 'team__division__season'
    )
    return [
        {
            "id": m.player.id,
            "first_name": m.player.first_name,
            "last_name": m.player.last_name,
            "jersey_number": m.jersey_number,
            "team_name": m.team.name,
            "team_id": m.team.id,
            "division_name": m.team.division.name,
            "season_name": m.team.division.season.name,
        }
        for m in memberships
    ]


@router.get("/organizations/{org_id}/volunteers", response=List[schemas.OrgVolunteerSchema])
def list_org_volunteers(request, org_id: UUID):
    staff_roles = ["COACH", "MANAGER", "SCORER", "ORG_ADMIN"]
    memberships = TeamMembership.objects.filter(
        team__division__season__organization_id=org_id,
        role__in=staff_roles,
        is_active=True
    ).select_related(
        'user', 'team__division__season'
    )
    return [
        {
            "user_id": m.user.id,
            "username": m.user.username,
            "email": m.user.email,
            "first_name": m.user.first_name,
            "last_name": m.user.last_name,
            "role": m.role,
            "team_name": m.team.name,
            "team_id": m.team.id,
            "division_name": m.team.division.name,
            "season_name": m.team.division.season.name,
        }
        for m in memberships
    ]


# --- ALERT ENDPOINTS ---
@router.get("/alerts", response=List[schemas.AlertSchema])
def list_alerts(request, org_id: UUID = None, division_id: int = None, team_id: UUID = None):
    qs = Alert.objects.filter(is_active=True)
    if org_id:
        qs = qs.filter(organization_id=org_id)
    if division_id:
        qs = qs.filter(division_id=division_id)
    if team_id:
        qs = qs.filter(team_id=team_id)
    qs = qs.select_related('created_by')
    return [
        {
            "id": a.id,
            "organization_id": a.organization_id,
            "division_id": a.division_id,
            "team_id": a.team_id,
            "title": a.title,
            "message": a.message,
            "created_by_username": a.created_by.username if a.created_by else "",
            "created_at": a.created_at.isoformat(),
        }
        for a in qs
    ]

@router.post("/alerts", response={201: schemas.AlertSchema, 403: dict})
def create_alert(request, data: schemas.AlertCreateSchema):
    if request.auth.profile.role not in ["ORG_OWNER", "ORG_ADMIN"]:
        return 403, {"message": "Only org owners and admins can create alerts."}
    alert = Alert.objects.create(
        organization_id=data.organization_id,
        division_id=data.division_id,
        team_id=data.team_id,
        title=data.title,
        message=data.message,
        created_by=request.auth,
    )
    return 201, {
        "id": alert.id,
        "organization_id": alert.organization_id,
        "division_id": alert.division_id,
        "team_id": alert.team_id,
        "title": alert.title,
        "message": alert.message,
        "created_by_username": request.auth.username,
        "created_at": alert.created_at.isoformat(),
    }

@router.put("/alerts/{alert_id}", response=schemas.AlertSchema)
def update_alert(request, alert_id: UUID, data: schemas.AlertCreateSchema):
    alert = get_object_or_404(Alert, id=alert_id)
    for attr in ('title', 'message', 'division_id', 'team_id'):
        setattr(alert, attr, getattr(data, attr))
    alert.save()
    return {
        "id": alert.id,
        "organization_id": alert.organization_id,
        "division_id": alert.division_id,
        "team_id": alert.team_id,
        "title": alert.title,
        "message": alert.message,
        "created_by_username": alert.created_by.username if alert.created_by else "",
        "created_at": alert.created_at.isoformat(),
    }

@router.delete("/alerts/{alert_id}", response={200: dict, 403: dict})
def delete_alert(request, alert_id: UUID):
    alert = get_object_or_404(Alert, id=alert_id)
    alert.is_active = False
    alert.save()
    return {"success": True}


# --- PLAYER ENDPOINTS ---
@router.get("/teams/{team_id}/players", response=List[profile_schemas.PlayerSchema])
def list_players(request, team_id: UUID):
    return Player.objects.filter(team_history__team_id=team_id).prefetch_related('team_history')