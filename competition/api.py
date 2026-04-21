from ninja import Router
from typing import List
from uuid import UUID
from django.shortcuts import get_object_or_404
from ninja_jwt.authentication import JWTAuth

from .models import Game
from . import schemas

router = Router(auth=JWTAuth())

# GET the schedule for a specific season
@router.get("/season/{season_id}/schedule", response=List[schemas.GameSchema])
def list_games(request, season_id: UUID):
    games = Game.objects.filter(season_id=season_id).select_related('home_team', 'away_team')
    
    # We map the team names manually for the Android UI
    return [{
        **g.__dict__,
        "home_team_name": g.home_team.name,
        "away_team_name": g.away_team.name,
    } for g in games]

# POST a new game
@router.post("/games", response={201: schemas.GameSchema})
def create_game(request, data: schemas.GameCreateSchema):
    game = Game.objects.create(**data.dict())
    return 201, game

@router.post("/games/{game_id}/score", response=schemas.GameSchema)
def record_score(request, game_id: UUID, home_score: int, away_score: int):
    game = get_object_or_404(Game, id=game_id)
    game.home_score = home_score
    game.away_score = away_score
    game.is_completed = True
    game.save()
    
    # This is a great place to trigger a standings update if you 
    # decide to cache standings in a table later.
    return game


@router.patch("/games/{game_id}/live-update")
def live_update(request, game_id: UUID, data: schemas.GameLiveUpdateSchema):
    game = get_object_or_404(Game, id=game_id)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(game, attr, value)
    game.save()
    return game    

@router.patch("/games/{game_id}/live-update", response=schemas.GameSchema)
def live_update_game(request, game_id: UUID, data: schemas.GameLiveUpdateSchema):
    game = get_object_or_404(Game, id=game_id)
    
    # Role-Based Access Control (RBAC)
    user_profile = request.user.profile
    allowed_roles = ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN', 'SCORER']
    
    if user_profile.role not in allowed_roles:
        return 403, {"message": "Unauthorized: You do not have scoring permissions."}

    # Update only the fields provided by the Android app
    update_data = data.dict(exclude_unset=True)
    for attr, value in update_data.items():
        setattr(game, attr, value)
    
    game.save()
    
    # Map names for the display (Android-friendly)
    return {
        **game.__dict__,
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
    }