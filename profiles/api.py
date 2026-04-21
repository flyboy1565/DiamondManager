from ninja import Router
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from ninja_jwt.authentication import JWTAuth
from typing import List, Optional
from uuid import UUID

import profiles.schemas as schemas
from .models import Profile, TeamMembership, Player

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
    return query.select_related('team', 'team__season', 'team__season__organization')

@router.get("/my-memberships", response=List[schemas.TeamMembershipSchema])
def get_my_memberships(request):
    # This grabs the user's teams, including the Org and Season names
    return TeamMembership.objects.filter(user=request.user).select_related(
        'team__season__organization'
    ).order_by('-is_active', '-joined_at')

@router.get("/my-kids", response=List[schemas.PlayerSchema])
def get_my_kids(request):
    # Grabs all players where the logged-in user is the guardian
    return Player.objects.filter(guardian=request.user).prefetch_related(
        'team_history__team__season__organization'
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
def update_player(request, player_id: UUID, data: schemas.PlayerUpdateSchema):
    player = get_object_or_404(Player, id=player_id)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(player, attr, value)
    player.save()
    return player

@router.delete("/players/{player_id}")
def delete_player(request, player_id: UUID):
    get_object_or_404(Player, id=player_id).delete()
    return {"success": True}