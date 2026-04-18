from ninja import Router
from typing import List
from uuid import UUID
from django.shortcuts import get_object_or_404
from .models import Game
from . import schemas

router = Router()

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