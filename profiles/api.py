import secrets
from ninja import Router
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User 
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from ninja_jwt.authentication import JWTAuth
from typing import List, Optional
from uuid import UUID
from datetime import timedelta

import profiles.schemas as schemas
from leagues.models import Team
from .models import Profile, TeamMembership, Player, Invitation

router = Router(auth=JWTAuth())

@router.get("/me", response=schemas.ProfileSchema)
def get_my_profile(request):
    # request.user is now automatically populated via the JWT
    return request.user.profile

# UPDATE profile (e.g., changing phone number or name)
@router.put("/me", response=schemas.ProfileSchema)
def update_my_profile(request, data: schemas.ProfileUpdateSchema):
    profile = get_object_or_404(Profile, user=request.user)
    user = request.user
    
    # Update User model fields if provided
    if data.first_name: user.first_name = data.first_name
    if data.last_name: user.last_name = data.last_name
    user.save()
    
    # Update Profile model fields
    if data.phone_number: profile.phone_number = data.phone_number
    # Note: Generally, users shouldn't change their own role! 
    # That would be handled by an Admin endpoint.
    profile.save()
    
    return profile

# ADMIN: Update a specific user's role
@router.patch("/{user_id}/role", response=schemas.ProfileSchema)
def change_user_role(request, user_id: int, role: str):
    # We will add an "is_staff" check here later
    profile = get_object_or_404(Profile, user_id=user_id)
    profile.role = role
    profile.save()
    return profile

@router.get("/my-teams", response=List[schemas.TeamMembershipSchema])
def get_my_teams(request, active_only: bool = False):
    query = TeamMembership.objects.filter(user=request.user)
    if active_only:
        query = query.filter(is_active=True)
    return query.select_related('team', 'team__division__season__organization')

@router.get("/my-memberships", response=List[schemas.TeamMembershipSchema])
def get_my_memberships(request):
    # This grabs the user's teams, including the Org and Season names
    return TeamMembership.objects.filter(user=request.user).select_related(
        'team__division__season__organization'
    ).order_by('-is_active', '-joined_at')

@router.get("/my-kids", response=List[schemas.PlayerSchema])
def get_my_kids(request):
    # Grabs all players where the logged-in user is the guardian
    return Player.objects.filter(guardian=request.user).prefetch_related(
        'team_history__team__division__season__organization'
    )    


@router.post("/players", response={201: schemas.PlayerSchema})
def create_player(request, data: schemas.PlayerCreateSchema):
    # 1. Create the Player
    player = Player.objects.create(
        first_name=data.first_name,
        last_name=data.last_name,
        guardian=request.user
    )
    
    # 2. Create the Membership if a team_id was provided
    if data.team_id:
        from .models import PlayerMembership
        PlayerMembership.objects.create(
            player=player,
            team_id=data.team_id,
            jersey_number=data.jersey_number
        )
    
    return 201, player

@router.put("/players/{player_id}", response=schemas.PlayerSchema)
def update_player(request, player_id: int, data: schemas.PlayerUpdateSchema):
    player = get_object_or_404(Player, id=player_id)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(player, attr, value)
    player.save()
    return player

@router.delete("/players/{player_id}")
def delete_player(request, player_id: int):
    get_object_or_404(Player, id=player_id).delete()
    return {"success": True}



@router.post("/invitations", response={201: dict, 403: dict})
def create_invitation(request, data: schemas.InvitationCreateSchema):
    # Enforce role boundaries using your custom Profile choices
    if request.user.profile.role not in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN', 'COACH', 'MANAGER']:
        return 403, {"message": "Dugout access denied: insufficient staff permissions."}
        
    # Standardize string processing
    clean_email = data.email.strip().lower()
    
    # Initialize auto-expiring secure token
    token_str = secrets.token_urlsafe(32)
    expiration = timezone.now() + timedelta(days=7)
    
    invitation = Invitation.objects.create(
        email=clean_email,
        token=token_str,
        team_id=data.team_id,
        player_id=data.player_id,
        target_role=data.target_role,
        invited_by=request.user,
        expires_at=expiration
    )
    
    return 201, {
        "id": invitation.id, 
        "token": invitation.token, 
        "message": f"Invitation generated cleanly for {clean_email}"
    }

# 2. VERIFY A TOKEN (Public Endpoint for Device Discovery)
@router.get("/invitations/verify/{token}", auth=None, response={200: dict, 400: dict})
def verify_invitation(request, token: str):
    invitation = Invitation.objects.filter(token=token).select_related('team', 'player').first()
    
    if not invitation or invitation.is_accepted or timezone.now() > invitation.expires_at:
        return 400, {"message": "This onboarding token is explicitly expired or invalid."}
        
    user_exists = User.objects.filter(email=invitation.email).exists()
        
    return 200, {
        "email": invitation.email,
        "team_name": invitation.team.name if invitation.team else None,
        "role": invitation.target_role,
        "player_name": f"{invitation.player.first_name} {invitation.player.last_name}" if invitation.player else None,
        "user_exists": user_exists
    }

def _assign_profile_organization_from_team(user, team):
    if not team:
        return

    season = getattr(team, 'season', None)
    organization = getattr(season, 'organization', None)
    if not organization:
        return

    profile = user.profile
    if profile.organization is None:
        profile.organization = organization
        profile.save()


# 3. ATOMIC ACCEPTANCE & GRAPH ACCOUNT BUILDING
@router.post("/invitations/accept", auth=None, response={201: dict, 200: dict, 400: dict})
def accept_invitation(request, data: schemas.InvitationAcceptSchema):
    invitation = Invitation.objects.filter(token=data.token).first()
    
    if not invitation or invitation.is_accepted or timezone.now() > invitation.expires_at:
        return 400, {"message": "Invalid or inactive registration token."}
        
    existing_user = User.objects.filter(email=invitation.email).first()

    with transaction.atomic():
        if existing_user:
            # === returning user path ===
            if invitation.player and invitation.target_role == 'PARENT':
                player = invitation.player
                player.guardian = existing_user
                player.save()
            
            if invitation.team:
                TeamMembership.objects.get_or_create(
                    user=existing_user, team=invitation.team, role=invitation.target_role,
                    defaults={'is_active': True}
                )
                _assign_profile_organization_from_team(existing_user, invitation.team)
                
            invitation.is_accepted = True
            invitation.save()
            return 200, {"success": True, "message": "Welcome back! Account context linked to the new season."}
            
        else:
            # === brand new user path ===
            if not data.username or not data.password:
                return 400, {"message": "Credentials are required for fresh profiles."}
            if User.objects.filter(username=data.username).exists():
                return 400, {"message": "Username is already claimed."}
                
            new_user = User.objects.create_user(
                username=data.username, email=invitation.email, password=data.password,
                first_name=data.first_name, last_name=data.last_name
            )
            
            # Update role generated by your signal auto-handler
            profile = new_user.profile #
            profile.role = invitation.target_role
            profile.save()
            
            if invitation.player and invitation.target_role == 'PARENT':
                player = invitation.player
                player.guardian = new_user
                player.save()
                
            if invitation.team:
                TeamMembership.objects.create(
                    user=new_user, team=invitation.team, role=invitation.target_role, is_active=True
                )
                _assign_profile_organization_from_team(new_user, invitation.team)
                
            invitation.is_accepted = True
            invitation.save()
            return 201, {"success": True, "message": "User ecosystem profile established cleanly."}

# 4. FAN PASS: PUBLIC ACCESS CODES
@router.post("/teams/join-as-follower", response={200: dict, 400: dict})
def join_team_as_follower(request, data: schemas.JoinTeamByCodeSchema):
    team = Team.objects.filter(access_code=data.access_code.upper().strip()).first()
    
    if not team:
        return 400, {"message": "Invalid team access code."}
        
    membership, created = TeamMembership.objects.get_or_create(
        user=request.user, team=team, role='FOLLOWER',
        defaults={'is_active': True}
    )
    
    return 200, {
        "success": True, "team_name": team.name, 
        "message": f"Successfully initialized fan pass for the {team.name}."
    }