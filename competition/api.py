import secrets
from datetime import timedelta
from ninja import Router
from typing import List
from uuid import UUID
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from ninja_jwt.authentication import JWTAuth

from .models import Game, ScoringToken
from . import schemas

router = Router(auth=JWTAuth())


def _can_score(request, game):
    """Check if the user is allowed to record scoring actions."""
    user = request.user
    if not user or not user.is_authenticated:
        return False
    if user.profile.role in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN', 'SCORER']:
        return True
    coaches = list(game.home_team.coaches.all()) + list(game.away_team.coaches.all())
    if user in coaches:
        return True
    return False


def _game_to_dict(game):
    return {
        **game.__dict__,
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
    }


def _init_scoring_data(game):
    """Initialize scoring_data with lineup info if empty."""
    if not game.scoring_data or not game.scoring_data.get('lineup_order'):
        from .models import GameLineupEntry
        for side_field, side_label in [('home_team', 'home'), ('away_team', 'away')]:
            team = getattr(game, side_field)
            entries = GameLineupEntry.objects.filter(game=game, team=team).order_by('batting_order')
            player_ids = [e.player_id for e in entries]
            game.scoring_data.setdefault('lineup_order', {})[side_label] = player_ids
        game.scoring_data.setdefault('batting_order_idx', {'home': 0, 'away': 0})
        game.scoring_data.setdefault('current_batter', None)
        game.scoring_data.setdefault('runners', {'first': None, 'second': None, 'third': None})
        game.scoring_data.setdefault('pitches', [])
        game.save(update_fields=['scoring_data'])


def _get_current_batter_player_id(game, side):
    idx = game.scoring_data.get('batting_order_idx', {}).get(side, 0)
    lineup = game.scoring_data.get('lineup_order', {}).get(side, [])
    if not lineup:
        return None
    if idx >= len(lineup):
        idx = 0
        game.scoring_data['batting_order_idx'][side] = 0
    return lineup[idx]


def _get_player_name(player_id):
    from profiles.models import Player
    try:
        p = Player.objects.get(id=player_id)
        return f"{p.first_name} {p.last_name}"
    except Player.DoesNotExist:
        return "Unknown"


def _advance_batter(game, side):
    idx = game.scoring_data.get('batting_order_idx', {}).get(side, 0)
    lineup = game.scoring_data.get('lineup_order', {}).get(side, [])
    if lineup:
        idx = (idx + 1) % len(lineup)
    game.scoring_data['batting_order_idx'][side] = idx
    pid = _get_current_batter_player_id(game, side)
    if pid:
        game.scoring_data['current_batter'] = {
            'side': side,
            'player_id': pid,
            'player_name': _get_player_name(pid),
        }


def _advance_inning(game):
    if game.is_top_inning:
        game.is_top_inning = False
    else:
        game.is_top_inning = True
        game.current_inning += 1
    game.outs = 0
    game.balls = 0
    game.strikes = 0
    game.scoring_data['runners'] = {'first': None, 'second': None, 'third': None}
    side = 'home' if not game.is_top_inning else 'away'
    _advance_batter(game, side)


def _reset_count(game):
    game.balls = 0
    game.strikes = 0


def _apply_record_pitch(game, pitch_type):
    snapshot = {
        'balls': game.balls,
        'strikes': game.strikes,
        'outs': game.outs,
        'home': game.home_score,
        'away': game.away_score,
    }

    side = 'home' if not game.is_top_inning else 'away'

    if pitch_type == 'ball':
        game.balls += 1
        if game.balls >= 4:
            game.balls = 0
            game.strikes = 0
            game.outs += 1
            if game.outs >= 3:
                _advance_inning(game)
            else:
                _advance_batter(game, side)

    elif pitch_type == 'strike':
        game.strikes += 1
        if game.strikes >= 3:
            game.outs += 1
            _reset_count(game)
            if game.outs >= 3:
                _advance_inning(game)
            else:
                _advance_batter(game, side)

    elif pitch_type == 'foul':
        if game.strikes < 2:
            game.strikes += 1

    elif pitch_type == 'hit':
        game.outs += 1
        _reset_count(game)
        if game.outs >= 3:
            _advance_inning(game)
        else:
            _advance_batter(game, side)

    game.pitch_count += 1

    pitch_record = {
        'id': len(game.scoring_data.get('pitches', [])) + 1,
        'inning': game.current_inning,
        'is_top': game.is_top_inning,
        'result': {'type': pitch_type},
        'before': snapshot,
        'timestamp': timezone.now().isoformat(),
    }
    game.scoring_data.setdefault('pitches', []).append(pitch_record)

# GET the schedule for a specific season
@router.get("/season/{season_id}/schedule", response=List[schemas.GameSchema])
def list_games(request, season_id: UUID):
    games = Game.objects.filter(season_id=season_id).select_related('home_team', 'away_team')
    return [{
        **g.__dict__,
        "home_team_name": g.home_team.name,
        "away_team_name": g.away_team.name,
    } for g in games]

# GET the schedule for a specific team
@router.get("/team/{team_id}/schedule", response=List[schemas.GameSchema])
def get_team_schedule(request, team_id: UUID):
    games = Game.objects.filter(
        Q(home_team_id=team_id) | Q(away_team_id=team_id)
    ).select_related('home_team', 'away_team')
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


@router.post("/games/{game_id}/set-batter", response=schemas.GameSchema)
def set_batter(request, game_id: UUID, data: schemas.SetBatterSchema):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized: You do not have scoring permissions."}

    _init_scoring_data(game)
    side = data.side

    if data.skip:
        _advance_batter(game, side)
    elif data.player_id:
        game.scoring_data['current_batter'] = {
            'side': side,
            'player_id': data.player_id,
            'player_name': _get_player_name(data.player_id),
        }
        # Also update the batting_order_idx to match
        lineup = game.scoring_data.get('lineup_order', {}).get(side, [])
        if data.player_id in lineup:
            game.scoring_data['batting_order_idx'][side] = lineup.index(data.player_id)

    game.save()
    return _game_to_dict(game)


@router.post("/games/{game_id}/record-pitch", response=schemas.GameSchema)
def record_pitch(request, game_id: UUID, data: schemas.RecordPitchSchema):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized: You do not have scoring permissions."}

    _init_scoring_data(game)

    # Set the game live on first pitch
    if not game.is_live:
        game.is_live = True

    _apply_record_pitch(game, data.type)
    game.save()
    return _game_to_dict(game)


@router.post("/games/{game_id}/undo-last-pitch", response=schemas.GameSchema)
def undo_last_pitch(request, game_id: UUID):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized: You do not have scoring permissions."}

    pitches = game.scoring_data.get('pitches', [])
    if not pitches:
        return 400, {"message": "No pitches to undo."}

    last = pitches.pop()
    before = last.get('before', {})
    game.balls = before.get('balls', 0)
    game.strikes = before.get('strikes', 0)
    game.outs = before.get('outs', 0)
    game.home_score = before.get('home', 0)
    game.away_score = before.get('away', 0)
    game.pitch_count = max(0, game.pitch_count - 1)

    # Restore inning state from the previous pitch or init
    if pitches:
        prev = pitches[-1]
        game.current_inning = prev.get('inning', 1)
        game.is_top_inning = prev.get('is_top', True)
    else:
        game.current_inning = 1
        game.is_top_inning = True

    game.save()
    return _game_to_dict(game)


@router.post("/games/{game_id}/scoring-link", response={200: dict, 403: dict})
def create_scoring_link(request, game_id: UUID):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Only coaches and scorers can generate scoring links."}

    token_str = secrets.token_urlsafe(32)
    expiration = timezone.now() + timedelta(hours=4)

    ScoringToken.objects.create(
        game=game,
        token=token_str,
        created_by=request.user,
        expires_at=expiration,
        is_active=True,
    )

    return 200, {
        "token": token_str,
        "url": f"diamondmanager://score/{token_str}",
    }


@router.post("/games/{game_id}/score-via-token/{token}", response=schemas.GameSchema, auth=None)
def score_via_token(request, game_id: UUID, token: str, data: schemas.RecordPitchSchema):
    game = get_object_or_404(Game, id=game_id)
    scoring_token = get_object_or_404(ScoringToken, token=token, game=game, is_active=True)

    if timezone.now() > scoring_token.expires_at:
        scoring_token.is_active = False
        scoring_token.save()
        return 400, {"message": "Scoring token has expired."}

    _init_scoring_data(game)

    if not game.is_live:
        game.is_live = True

    _apply_record_pitch(game, data.type)
    game.save()
    return _game_to_dict(game)


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