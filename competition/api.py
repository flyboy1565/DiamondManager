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


@router.get("/games/{game_id}", response=schemas.GameSchema)
def get_game(request, game_id: UUID):
    game = get_object_or_404(Game, id=game_id)
    return {
        **game.__dict__,
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
    }


@router.get("/games/{game_id}/lineup", response=List[schemas.LineupEntrySchema])
def get_game_lineup(request, game_id: UUID):
    game = get_object_or_404(Game, id=game_id)
    entries = game.lineup_entries.select_related('team', 'player').all()
    return [
        {
            "id": entry.id,
            "team_id": entry.team.id,
            "team_name": entry.team.name,
            "player_id": entry.player.id,
            "player_name": f"{entry.player.first_name} {entry.player.last_name}",
            "batting_order": entry.batting_order,
            "position": entry.position,
            "is_active": entry.is_active,
        }
        for entry in entries
    ]


@router.get("/games/{game_id}/scoreboard", response=schemas.GameSchema)
def get_game_scoreboard(request, game_id: UUID):
    return get_game(request, game_id)


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


@router.get("/rulebook", response=List[schemas.RuleSchema])
def get_rulebook(request):
    return [
        {
            "title": "Pitching limits by age",
            "description": "9U and 10U: 50 pitches/day; 11U and 12U: 70 pitches/day; 13U+: 90 pitches/day.",
            "category": "Pitching",
        },
        {
            "title": "Maximum game length",
            "description": "Seven innings or two hours max. No new inning starts after 1 hour 50 minutes.",
            "category": "Game Play",
        },
        {
            "title": "Substitution rules",
            "description": "Free substitution is allowed; batting order stays fixed unless a player is injured.",
            "category": "Roster",
        },
        {
            "title": "Batting order changes",
            "description": "Lineups must be submitted before the game. No changes after the game starts except for injury replacement.",
            "category": "Batting",
        },
        {
            "title": "Base running",
            "description": "Runners may steal only after the pitch crosses the plate. Early leads are enforced.",
            "category": "Base Running",
        },
    ]