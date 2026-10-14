from typing import List, Optional
from datetime import datetime, timedelta
import secrets
import uuid

from ninja import Router, Schema
from pydantic import UUID4 as UUID
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings

from .models import TeamEvent, Game, GameLineupEntry, ScoringToken
from .schemas import (
    TeamEventSchema, TeamEventCreateSchema, TeamEventUpdateSchema,
    GameSchema, LineupEntrySchema, LineupEntryCreateSchema,
    RecordPitchSchema, NonPitchSchema, SetPitcherSchema, BatterSchema,
    ScoreUpdateSchema, ScoringTokenSchema, ScoreboardSchema, GameScoreDetailSchema,
    OrganizationSettingsSchema,
    StreamStartResponseSchema,
)
from .permissions import (
    IsOrgOwnerOrAdmin, IsGameManagerOrScorekeeper, IsEventCreatorOrAdmin,
    require_team_manager_or_scorekeeper, require_event_creator_or_admin,
    can_schedule_game, can_manage_event
)
from .scheduling import (
    get_week_range, team_event_count, team_can_add_events,
    check_location_conflict
)
from . import schemas
from profiles.models import Profile
from leagues.models import Team, Division, Organization
from .streaming.youtube import YouTubeLiveService, YouTubeConfigError
from .streaming import relay
from .streaming.relay import RelayError, relay_enabled
from .streaming import oauth

router = Router(auth=JWTAuth())


def _get_user_profile(request):
    try:
        return Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        return None



_BALL_TYPES = {'ball', 'ball_outside', 'ball_inside', 'ball_high', 'ball_low', 'ball_dirt'}
_STRIKE_TYPES = {'strike', 'strike_called', 'strike_swinging', 'strike_foul_tip'}
_OUT_TYPES = {'out', 'out_ground', 'out_fly', 'out_line', 'out_pop', 'strikeout'}
_RUNNER_EVENTS = {'steal', 'caught_stealing', 'balk', 'pickoff'}
_BASE_INDEX = {'first': 1, 'second': 2, 'third': 3}
_INDEX_BASE = {1: 'first', 2: 'second', 3: 'third'}


def _batting_side(game):
    # Top of the inning: away team bats. Bottom: home team bats.
    return 'away' if game.is_top_inning else 'home'


def _score_field(side):
    return 'away_score' if side == 'away' else 'home_score'


def _runners(game):
    sd = game.scoring_data
    runners = sd.get('runners')
    if not isinstance(runners, dict):
        runners = {'first': None, 'second': None, 'third': None}
        sd['runners'] = runners
    for base in ('first', 'second', 'third'):
        runners.setdefault(base, None)
    return runners


def _batter_dict(game):
    cb = game.scoring_data.get('current_batter') or {}
    pid = cb.get('player_id')
    if pid is None:
        return {'player_id': None, 'player_name': ''}
    return {'player_id': pid, 'player_name': cb.get('player_name') or _get_player_name(pid)}


def _add_run(game, side, count=1):
    field = _score_field(side)
    setattr(game, field, (getattr(game, field) or 0) + count)
    innings = game.scoring_data.setdefault('innings', {})
    key = str(game.current_inning or 1)
    slot = innings.setdefault(key, {'home': 0, 'away': 0})
    slot[side] = slot.get(side, 0) + count


def _advance_all(game, bases):
    """Advance every runner on base by ``bases``; runners reaching home score."""
    runners = _runners(game)
    side = _batting_side(game)
    new = {'first': None, 'second': None, 'third': None}
    for base in ('third', 'second', 'first'):
        runner = runners.get(base)
        if not runner:
            continue
        dest = _BASE_INDEX[base] + bases
        if dest >= 4:
            _add_run(game, side)
        else:
            new[_INDEX_BASE[dest]] = runner
    runners.update(new)


def _place_batter(game, base):
    _runners(game)[base] = _batter_dict(game)


def _award_first(game):
    """Walk/HBP: put batter on first, forcing runners ahead."""
    runners = _runners(game)
    batter = _batter_dict(game)
    if not runners['first']:
        runners['first'] = batter
    elif not runners['second']:
        runners['second'] = runners['first']
        runners['first'] = batter
    elif not runners['third']:
        runners['third'] = runners['second']
        runners['second'] = runners['first']
        runners['first'] = batter
    else:
        _add_run(game, _batting_side(game))
        runners['third'] = runners['second']
        runners['second'] = runners['first']
        runners['first'] = batter


def _lead_runner_base(game):
    runners = _runners(game)
    for base in ('third', 'second', 'first'):
        if runners.get(base):
            return base
    return None


def _remove_runner(game, base):
    runners = _runners(game)
    value = runners.get(base)
    runners[base] = None
    return value


def _remove_lead_runner(game):
    base = _lead_runner_base(game)
    if base:
        _remove_runner(game, base)
    return base


def _clear_runners(game):
    runners = _runners(game)
    runners['first'] = runners['second'] = runners['third'] = None


def _steal(game, base):
    if base not in _BASE_INDEX:
        return
    runners = _runners(game)
    runner = runners.get(base)
    if not runner:
        return
    runners[base] = None
    if base == 'first':
        runners['second'] = runner
    elif base == 'second':
        runners['third'] = runner
    else:
        _add_run(game, _batting_side(game))


def _record_out(game, count=1):
    game.outs = (game.outs or 0) + count


def _reset_count(game):
    game.balls = 0
    game.strikes = 0


def _check_inning_change(game):
    if (game.outs or 0) >= 3:
        game.outs = 0
        game.balls = 0
        game.strikes = 0
        _clear_runners(game)
        if game.is_top_inning:
            game.is_top_inning = False
        else:
            game.is_top_inning = True
            game.current_inning = (game.current_inning or 1) + 1


def _record_pitch_stat(game, side):
    if side not in ('home', 'away'):
        return
    pitchers = game.scoring_data.setdefault('pitchers', {})
    pitcher = (game.scoring_data.get('current_pitcher') or {}).get(side)
    if not pitcher:
        return
    pid = pitcher.get('player_id')
    if pid is None:
        return
    key = str(pid)
    slot = pitchers.setdefault(key, {'pitch_count': 0, 'name': pitcher.get('player_name', '')})
    slot['pitch_count'] = slot.get('pitch_count', 0) + 1


def _record_batter_atbat(game, side, hit=False, home_run=False, hit_by_pitch=False):
    cb = game.scoring_data.get('current_batter') or {}
    pid = cb.get('player_id')
    if pid is not None:
        batters = game.scoring_data.setdefault('batters', {})
        slot = batters.setdefault(str(pid), {
            'at_bats': 0, 'hits': 0, 'home_runs': 0, 'name': cb.get('player_name', '')
        })
        if not hit_by_pitch:
            slot['at_bats'] = slot.get('at_bats', 0) + 1
        if hit:
            slot['hits'] = slot.get('hits', 0) + 1
        if home_run:
            slot['home_runs'] = slot.get('home_runs', 0) + 1
    _advance_batter(game, side)


def _apply_record_pitch(game, pitch_type, extra=None):
    extra = extra or {}
    if not isinstance(game.scoring_data, dict):
        game.scoring_data = {}
    game.balls = game.balls or 0
    game.strikes = game.strikes or 0
    game.outs = game.outs or 0
    game.pitch_count = game.pitch_count or 0
    side = _batting_side(game)
    pitch = pitch_type

    if pitch not in _RUNNER_EVENTS:
        game.pitch_count += 1
        _record_pitch_stat(game, side)

    if pitch in _BALL_TYPES:
        game.balls += 1
        if game.balls >= 4:
            _award_first(game)
            _reset_count(game)
    elif pitch in _STRIKE_TYPES:
        game.strikes += 1
        if game.strikes >= 3:
            _record_out(game, 1)
            _reset_count(game)
            _record_batter_atbat(game, side)
    elif pitch == 'foul':
        if game.strikes < 2:
            game.strikes += 1
    elif pitch == 'bunt_foul':
        if game.strikes >= 2:
            _record_out(game, 1)
            _reset_count(game)
            _record_batter_atbat(game, side)
        else:
            game.strikes += 1
    elif pitch == 'hit_by_pitch':
        _award_first(game)
        _reset_count(game)
        _record_batter_atbat(game, side, hit_by_pitch=True)
    elif pitch in ('single', 'hit'):
        _advance_all(game, 1)
        _place_batter(game, 'first')
        _reset_count(game)
        _record_batter_atbat(game, side, hit=True)
    elif pitch == 'double':
        _advance_all(game, 2)
        _place_batter(game, 'second')
        _reset_count(game)
        _record_batter_atbat(game, side, hit=True)
    elif pitch == 'triple':
        _advance_all(game, 3)
        _place_batter(game, 'third')
        _reset_count(game)
        _record_batter_atbat(game, side, hit=True)
    elif pitch == 'homerun':
        _advance_all(game, 4)
        _add_run(game, side)
        _reset_count(game)
        _record_batter_atbat(game, side, hit=True, home_run=True)
    elif pitch in _OUT_TYPES:
        _record_out(game, 1)
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch == 'double_play':
        removed = _remove_lead_runner(game)
        _record_out(game, 2 if removed else 1)
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch == 'triple_play':
        _clear_runners(game)
        _record_out(game, 3)
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch == 'pickoff':
        base = extra.get('runner_base') or _lead_runner_base(game)
        if base:
            _remove_runner(game, base)
            _record_out(game, 1)
    elif pitch == 'steal':
        _steal(game, extra.get('runner_base') or _lead_runner_base(game))
    elif pitch == 'caught_stealing':
        base = extra.get('runner_base') or _lead_runner_base(game)
        if base:
            _remove_runner(game, base)
            _record_out(game, 1)
    elif pitch == 'sac_bunt':
        _advance_all(game, 1)
        _record_out(game, 1)
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch == 'sac_fly':
        runners = _runners(game)
        if runners.get('third'):
            _add_run(game, side)
            runners['third'] = None
        _record_out(game, 1)
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch == 'error':
        _advance_all(game, 1)
        _place_batter(game, 'first')
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch == 'fielders_choice':
        runners = _runners(game)
        if runners.get('first'):
            runners['first'] = None
        _place_batter(game, 'first')
        _record_out(game, 1)
        _reset_count(game)
        _record_batter_atbat(game, side)
    elif pitch in ('wild_pitch', 'passed_ball', 'balk'):
        _advance_all(game, 1)
    elif pitch == 'dropped_third_strike':
        runners = _runners(game)
        if runners.get('first') and (game.outs or 0) < 2:
            _record_out(game, 1)
            _record_batter_atbat(game, side)
        else:
            _award_first(game)
            _record_batter_atbat(game, side, hit_by_pitch=True)
        _reset_count(game)
    elif pitch == 'infield_fly':
        _record_out(game, 1)
        _reset_count(game)
        _record_batter_atbat(game, side)

    _check_inning_change(game)
    game.save()


def _init_scoring_data(game, force=False):
    sd = game.scoring_data if isinstance(game.scoring_data, dict) else {}
    if sd.get('initialized') and not force:
        return
    game.current_inning = 1
    game.is_top_inning = True
    game.outs = 0
    game.balls = 0
    game.strikes = 0
    game.pitch_count = 0
    game.home_score = 0
    game.away_score = 0
    game.is_live = True
    game.is_completed = False
    game.scoring_data = {
        'initialized': True,
        'innings': {},
        'batters': {},
        'pitchers': {},
        'current_batter': None,
        'current_pitcher': None,
        'runners': {'first': None, 'second': None, 'third': None},
        'lineup_order': sd.get('lineup_order', {'home': [], 'away': []}),
        'batting_order_idx': sd.get('batting_order_idx', {'home': 0, 'away': 0}),
    }
    game.save()


def _get_player_name(player_id):
    if player_id is None:
        return ''
    try:
        from profiles.models import Player
        player = Player.objects.filter(id=player_id).first()
        return str(player) if player else ''
    except Exception:
        return ''


def _advance_batter(game, side):
    sd = game.scoring_data if isinstance(game.scoring_data, dict) else {}
    lineup = (sd.get('lineup_order') or {}).get(side) or []
    if not lineup:
        return
    idx = (sd.get('batting_order_idx') or {}).get(side, 0)
    idx = (idx + 1) % len(lineup)
    sd.setdefault('batting_order_idx', {})[side] = idx
    pid = lineup[idx]
    sd['current_batter'] = {
        'side': side,
        'player_id': pid,
        'player_name': _get_player_name(pid),
    }


def _get_current_batter_player_id(game, side):
    sd = game.scoring_data if isinstance(game.scoring_data, dict) else {}
    lineup = (sd.get('lineup_order') or {}).get(side) or []
    if not lineup:
        return None
    idx = (sd.get('batting_order_idx') or {}).get(side, 0)
    try:
        return lineup[idx % len(lineup)]
    except Exception:
        return None


def compute_game_stats(game):
    sd = game.scoring_data if isinstance(game.scoring_data, dict) else {}

    def _coerce(mapping):
        out = {}
        for key, value in (mapping or {}).items():
            try:
                key = int(key)
            except (TypeError, ValueError):
                pass
            out[key] = dict(value) if isinstance(value, dict) else value
        return out

    innings = {}
    for key, value in (sd.get('innings') or {}).items():
        try:
            key = int(key)
        except (TypeError, ValueError):
            pass
        value = value or {}
        innings[key] = {'home': value.get('home', 0), 'away': value.get('away', 0)}

    return {
        'batters': _coerce(sd.get('batters')),
        'pitchers': _coerce(sd.get('pitchers')),
        'innings': innings,
    }


def _game_to_dict(game):
    return {
        'id': game.id,
        'season_id': game.season_id,
        'home_team_id': game.home_team_id,
        'away_team_id': game.away_team_id,
        'home_team_name': game.home_team.name,
        'away_team_name': game.away_team.name,
        'date_time': game.date_time,
        'location': game.location,
        'home_score': game.home_score or 0,
        'away_score': game.away_score or 0,
        'is_live': game.is_live,
        'current_inning': game.current_inning or 1,
        'is_top_inning': game.is_top_inning,
        'outs': game.outs or 0,
        'balls': game.balls or 0,
        'strikes': game.strikes or 0,
        'pitch_count': game.pitch_count or 0,
        'is_completed': game.is_completed,
        'scoring_data': game.scoring_data,
        'stream_status': game.stream_status,
        'youtube_video_id': game.youtube_video_id,
    }

def _can_score(request, game):
    profile = _get_user_profile(request)
    roles = list(request.user.groups.values_list('name', flat=True)) if hasattr(request.user, 'groups') else []
    if request.user.is_superuser:
        return True
    if profile and profile.organization_id == game.season.organization_id:
        if getattr(profile, 'role', '') in ('ORG_ADMIN','SCOREKEEPER','SCORER') or any(r in ('ORG_ADMIN','TEAM_MANAGER','SCOREKEEPER','SCORER','OWNER') for r in roles):
            return True
    if any(r in ('OWNER','ORG_ADMIN','TEAM_MANAGER','SCOREKEEPER') for r in roles):
        return True
    return False

def _can_manage_org(request, org_id):
    if request.user.is_superuser:
        return True
    profile = _get_user_profile(request)
    roles = list(request.user.groups.values_list('name', flat=True)) if hasattr(request.user, 'groups') else []
    if profile and str(profile.organization_id) == str(org_id) and getattr(profile, 'role', '') in ('ORG_ADMIN', 'OWNER'):
        return True
    return any(r in ('ORG_ADMIN', 'OWNER') for r in roles)

def _build_stream_response(game):
    org = game.season.organization
    cfg = getattr(org, 'youtube_config', None)
    srt_base = cfg.streaming_server_srt_url if cfg and cfg.streaming_server_srt_url else getattr(settings, 'STREAMING_SERVER_SRT_URL_DEFAULT', '')
    if srt_base.startswith('srt://'):
        srt_url = srt_base
    else:
        srt_url = f"srt://{srt_base}" if srt_base else ''
    full_srt_url = f"{srt_url}?streamid={game.srt_stream_id}" if game.srt_stream_id else srt_url
    embed_url = f"https://www.youtube.com/embed/{game.youtube_video_id}" if game.youtube_video_id else ''
    return StreamStartResponseSchema(
        srt_url=srt_url,
        srt_stream_id=game.srt_stream_id or '',
        full_srt_url=full_srt_url,
        youtube_video_id=game.youtube_video_id or '',
        youtube_broadcast_id=game.youtube_broadcast_id or '',
        youtube_stream_id=game.youtube_stream_id or '',
        embed_url=embed_url,
        stream_status=game.stream_status,
        stream_error=game.stream_error or '',
    )


def _rollback_youtube_stream(svc, org, bcast, stream):
    if bcast and bcast.get('youtube_broadcast_id'):
        try:
            svc.delete_broadcast(org, bcast['youtube_broadcast_id'])
        except YouTubeConfigError:
            pass
    if stream and stream.get('youtube_stream_id'):
        try:
            svc.delete_stream(org, stream['youtube_stream_id'])
        except YouTubeConfigError:
            pass


@router.post("/games/{game_id}/stream/start", response=StreamStartResponseSchema)
def start_stream(request, game_id: str):
    from ninja.errors import HttpError
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        raise HttpError(403, "Permission denied")

    org = game.season.organization
    svc = YouTubeLiveService()
    bcast = None
    stream = None
    try:
        title = f"{game.home_team.name} vs {game.away_team.name} - {game.date_time.strftime('%Y-%m-%d %H:%M')}"
        bcast = svc.create_broadcast(org, title=title, description='', privacy_status=None)
        stream = svc.create_stream(org)
        svc.bind_broadcast(org, bcast['youtube_broadcast_id'], stream['youtube_stream_id'])
    except YouTubeConfigError as e:
        _rollback_youtube_stream(svc, org, bcast, stream)
        game.stream_status = 'error'
        game.stream_error = str(e)
        game.save(update_fields=['stream_status', 'stream_error'])
        raise HttpError(400, str(e))

    game.youtube_broadcast_id = bcast['youtube_broadcast_id']
    game.youtube_stream_id = stream['youtube_stream_id']
    game.youtube_video_id = bcast.get('youtube_video_id') or bcast['youtube_broadcast_id']
    game.srt_stream_id = f"live/game-{game.id}"
    game.stream_status = 'preparing'
    game.stream_started_at = timezone.now()
    game.stream_ended_at = None
    game.is_streaming_enabled = True
    game.stream_error = ''
    game.save(update_fields=[
        'youtube_broadcast_id', 'youtube_stream_id', 'youtube_video_id',
        'srt_stream_id', 'stream_status', 'stream_started_at', 'stream_ended_at',
        'is_streaming_enabled', 'stream_error',
    ])

    if relay_enabled():
        ingest_address = stream.get('ingestion_address')
        stream_key = stream.get('stream_key')
        if ingest_address and stream_key:
            try:
                relay.start_relay(game.srt_stream_id, ingest_address, stream_key)
            except RelayError as e:
                game.stream_status = 'error'
                game.stream_error = f"Relay start failed: {e}"
                game.save(update_fields=['stream_status', 'stream_error'])
                raise HttpError(502, game.stream_error)
        else:
            game.stream_error = 'YouTube did not return an ingest address/key'
            game.save(update_fields=['stream_error'])

    return _build_stream_response(game)


@router.post("/games/{game_id}/stream/stop")
def stop_stream(request, game_id: str):
    from ninja.errors import HttpError
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        raise HttpError(403, "Permission denied")

    if relay_enabled() and game.srt_stream_id:
        try:
            relay.stop_relay(game.srt_stream_id)
        except RelayError:
            pass

    if game.youtube_broadcast_id:
        try:
            YouTubeLiveService().complete_broadcast(game.season.organization, game.youtube_broadcast_id)
        except YouTubeConfigError:
            pass

    game.stream_status = 'ended'
    game.stream_ended_at = timezone.now()
    game.is_streaming_enabled = False
    game.save(update_fields=['stream_status', 'stream_ended_at', 'is_streaming_enabled'])
    return {"status": "ok", "stream_status": game.stream_status}


@router.get("/games/{game_id}/stream/status", response=StreamStartResponseSchema)
def stream_status(request, game_id: str):
    game = get_object_or_404(Game, id=game_id)
    return _build_stream_response(game)

@router.get("/games/{game_id}/scoreboard", response=schemas.GameScoreDetailSchema)
def get_scoreboard(request, game_id: UUID):
    game = get_object_or_404(Game, id=game_id)
    return schemas.GameScoreDetailSchema(
        id=game.id,
        home_team_name=game.home_team.name,
        away_team_name=game.away_team.name,
        home_score=game.home_score,
        away_score=game.away_score,
        current_inning=game.current_inning,
        is_top_inning=game.is_top_inning,
        outs=game.outs,
        balls=game.balls,
        strikes=game.strikes,
        pitch_count=game.pitch_count,
        is_live=game.is_live,
        is_completed=game.is_completed,
        scoring_data=game.scoring_data,
        date_time=game.date_time,
        location=game.location,
        stream_status=getattr(game, 'stream_status', None),
        youtube_video_id=getattr(game, 'youtube_video_id', None),
    )
# ------------------------------------------------------------------
# Scheduling API endpoints
# ------------------------------------------------------------------


@router.get("/teams/{team_id}/events", response=List[schemas.TeamEventSchema])
def list_team_events(request, team_id: UUID):
    from .models import TeamEvent
    events = TeamEvent.objects.filter(team_id=team_id).select_related(
        'team', 'opponent_team', 'division'
    ).order_by('-date_time')
    return [
        {
            "id": e.id,
            "scope": e.scope,
            "event_type": e.event_type,
            "title": e.title,
            "description": e.description,
            "date_time": e.date_time,
            "location": e.location,
            "status": e.status,
            "is_home_game": e.is_home_game,
            "home_score": e.home_score,
            "away_score": e.away_score,
            "counts_against_limit": e.counts_against_limit,
            "is_live": e.is_live,
            "current_inning": e.current_inning or 1,
            "is_top_inning": e.is_top_inning if e.is_top_inning is not None else True,
            "outs": e.outs or 0,
            "balls": e.balls or 0,
            "strikes": e.strikes or 0,
            "pitch_count": e.pitch_count or 0,
            "opponent_team_id": e.opponent_team_id,
            "opponent_team_name": e.opponent_team.name if e.opponent_team else None,
            "team_id": e.team_id,
            "team_name": e.team.name if e.team else None,
            "division_id": e.division_id,
            "division_name": e.division.name if e.division else None,
            "game_id": e.game_id,
        }
        for e in events
    ]


@router.post("/teams/{team_id}/events", response={201: schemas.TeamEventSchema, 403: dict, 429: dict})
def create_team_event(request, team_id: UUID, data: schemas.TeamEventCreateSchema):
    from .models import TeamEvent
    from leagues.models import Team
    from .scheduling import team_can_add_events, get_week_range

    team = get_object_or_404(Team, id=team_id)

    # Permission check
    from .permissions import can_create_event
    if not can_create_event(request.user, 'TEAM', data.event_type, team=team):
        return 403, {"message": "Unauthorized: You cannot create events for this team."}

    # Weekly limit check (only for countable events)
    if data.counts_against_limit:
        week_start, week_end = get_week_range(data.date_time)
        allowed, current, max_allowed = team_can_add_events(team, 1, week_start, week_end)
        if not allowed:
            return 429, {
                "message": f"Team at weekly limit ({current}/{max_allowed}).",
                "current": current,
                "max_allowed": max_allowed,
            }

    event = TeamEvent.objects.create(
        scope='TEAM',
        team=team,
        event_type=data.event_type,
        title=data.title,
        description=data.description or "",
        date_time=data.date_time,
        location=data.location or "",
        opponent_team_id=data.opponent_team_id,
        is_home_game=data.is_home_game,
        counts_against_limit=data.counts_against_limit,
        practice_focus=data.practice_focus,
        attendance_required=data.attendance_required,
        created_by=request.user,
        organization=team.division.season.organization,
        division=team.division,
    )
    return 201, {
        "id": event.id,
        "scope": event.scope,
        "event_type": event.event_type,
        "title": event.title,
        "description": event.description,
        "date_time": event.date_time,
        "location": event.location,
        "status": event.status,
        "is_home_game": event.is_home_game,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "counts_against_limit": event.counts_against_limit,
        "is_live": event.is_live,
        "current_inning": 1,
        "is_top_inning": True,
        "outs": 0,
        "balls": 0,
        "strikes": 0,
        "pitch_count": 0,
        "opponent_team_id": event.opponent_team_id,
        "opponent_team_name": team.name if event.opponent_team_id else None,
        "team_id": event.team_id,
        "team_name": team.name,
        "division_id": team.division_id,
        "division_name": team.division.name,
        "game_id": None,
    }


@router.put("/events/{event_id}", response={200: schemas.TeamEventSchema, 403: dict})
def update_team_event(request, event_id: UUID, data: schemas.TeamEventUpdateSchema):
    from .models import TeamEvent
    from .permissions import can_edit_event

    event = get_object_or_404(TeamEvent, id=event_id)
    if not can_edit_event(request.user, event):
        return 403, {"message": "Unauthorized: You cannot edit this event."}

    update_data = data.dict(exclude_unset=True)
    for attr, value in update_data.items():
        setattr(event, attr, value)
    event.save()

    return 200, {
        "id": event.id,
        "scope": event.scope,
        "event_type": event.event_type,
        "title": event.title,
        "description": event.description,
        "date_time": event.date_time,
        "location": event.location,
        "status": event.status,
        "is_home_game": event.is_home_game,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "counts_against_limit": event.counts_against_limit,
        "is_live": event.is_live,
        "current_inning": event.current_inning or 1,
        "is_top_inning": event.is_top_inning if event.is_top_inning is not None else True,
        "outs": event.outs or 0,
        "balls": event.balls or 0,
        "strikes": event.strikes or 0,
        "pitch_count": event.pitch_count or 0,
        "opponent_team_id": event.opponent_team_id,
        "opponent_team_name": event.opponent_team.name if event.opponent_team else None,
        "team_id": event.team_id,
        "team_name": event.team.name if event.team else None,
        "division_id": event.division_id,
        "division_name": event.division.name if event.division else None,
        "game_id": event.game_id,
    }


@router.delete("/events/{event_id}", response={200: dict, 403: dict})
def delete_team_event(request, event_id: UUID):
    from .models import TeamEvent
    from .permissions import can_delete_event

    event = get_object_or_404(TeamEvent, id=event_id)
    if not can_delete_event(request.user, event):
        return 403, {"message": "Unauthorized: You cannot delete this event."}

    event.delete()
    return 200, {"success": True}


@router.get("/divisions/{division_id}/weekly-status", response=schemas.WeeklyStatusSchema)
def get_weekly_status(request, division_id: int, year: int = None, month: int = None, day: int = None):
    from datetime import datetime
    from .scheduling import get_week_range, team_event_count
    from leagues.models import Division

    division = get_object_or_404(Division, id=division_id)
    org = division.season.organization
    max_allowed = org.max_events_per_team_per_week

    # Determine reference date
    if year and month and day:
        ref_date = datetime(year, month, day, tzinfo=timezone.now().tzinfo)
    else:
        ref_date = timezone.now()

    week_start, week_end = get_week_range(ref_date)
    teams = division.teams.all()

    team_statuses = []
    for team in teams:
        count = team_event_count(team, week_start, week_end)
        team_statuses.append({
            "team_id": team.id,
            "team_name": team.name,
            "current_count": count,
            "max_allowed": max_allowed,
            "remaining": max(0, max_allowed - count),
        })

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "max_allowed": max_allowed,
        "teams": team_statuses,
    }


@router.post("/admin/schedule-game", response={201: dict, 429: dict})
def schedule_game(request, data: schemas.ScheduleGameSchema):
    from .models import TeamEvent, Game
    from leagues.models import Team
    from .scheduling import team_can_add_events, get_week_range, get_location_conflicts
    from django.contrib import messages

    home_team = get_object_or_404(Team, id=data.home_team_id)
    away_team = get_object_or_404(Team, id=data.away_team_id)
    division = home_team.division

    # Weekly limit check for both teams
    week_start, week_end = get_week_range(data.date_time)
    for team, label in [(home_team, "Home"), (away_team, "Away")]:
        allowed, current, max_allowed = team_can_add_events(team, 1, week_start, week_end)
        if not allowed:
            return 429, {
                "message": f"{label} team {team.name} at weekly limit ({current}/{max_allowed}).",
                "team_id": str(team.id),
                "current": current,
                "max_allowed": max_allowed,
            }

    # Create Game model for scoring
    game = Game.objects.create(
        season=division.season,
        home_team=home_team,
        away_team=away_team,
        date_time=data.date_time,
        location=data.location or "",
    )

    # Create paired TeamEvents
    type_labels = dict(TeamEvent.EVENT_TYPE_CHOICES)
    type_label = type_labels.get(data.event_type, data.event_type)

    home_event = TeamEvent.objects.create(
        scope='TEAM',
        organization=division.season.organization,
        division=division,
        team=home_team,
        opponent_team=away_team,
        event_type=data.event_type,
        title=f"{home_team.name} vs {away_team.name}",
        description=f"{type_label}: {home_team.name} vs {away_team.name}",
        date_time=data.date_time,
        location=data.location or "",
        counts_against_limit=data.counts_against_limit,
        created_by=request.user,
        status='SCHEDULED',
        is_home_game=True,
        game=game,
    )

    away_event = TeamEvent.objects.create(
        scope='TEAM',
        organization=division.season.organization,
        division=division,
        team=away_team,
        opponent_team=home_team,
        event_type=data.event_type,
        title=f"{away_team.name} vs {home_team.name}",
        description=f"{type_label}: {away_team.name} @ {home_team.name}",
        date_time=data.date_time,
        location=data.location or "",
        counts_against_limit=data.counts_against_limit,
        created_by=request.user,
        status='SCHEDULED',
        is_home_game=False,
        game=game,
    )

    def _event_to_dict(e):
        return {
            "id": str(e.id),
            "event_type": e.event_type,
            "title": e.title,
            "description": e.description,
            "date_time": e.date_time.isoformat(),
            "location": e.location,
            "status": e.status,
            "is_home_game": e.is_home_game,
            "counts_against_limit": e.counts_against_limit,
            "team_id": str(e.team_id),
            "team_name": e.team.name,
            "opponent_team_id": str(e.opponent_team_id) if e.opponent_team_id else None,
            "opponent_team_name": e.opponent_team.name if e.opponent_team else None,
            "game_id": str(e.game_id) if e.game_id else None,
        }

    return 201, {
        "events": [_event_to_dict(home_event), _event_to_dict(away_event)],
        "game_id": str(game.id),
    }


@router.get("/location-conflicts", response=List[schemas.LocationConflictSchema])
def get_location_conflicts_api(
    request,
    location: str,
    date: str,
    division_id: int,
):
    from datetime import datetime as dt
    from .scheduling import get_location_conflicts

    date_obj = dt.strptime(date, "%Y-%m-%d").date()
    from leagues.models import Division
    division = get_object_or_404(Division, id=division_id)

    ref_dt = timezone.make_aware(dt.combine(date_obj, dt.min.time()))
    conflicts = get_location_conflicts(location, ref_dt, division)

    return [
        {
            "id": e.id,
            "team_name": e.team.name if e.team else "",
            "opponent_team_name": e.opponent_team.name if e.opponent_team else None,
            "date_time": e.date_time,
            "location": e.location,
            "event_type": e.event_type,
            "title": e.title,
        }
        for e in conflicts
    ]


@router.get("/organizations/{org_id}/settings", response=schemas.OrgSettingsSchema)
def get_org_settings(request, org_id: UUID):
    from leagues.models import Organization
    org = get_object_or_404(Organization, id=org_id)
    return {"max_events_per_team_per_week": org.max_events_per_team_per_week}


@router.put("/organizations/{org_id}/settings", response={200: schemas.OrgSettingsSchema, 403: dict})
def update_org_settings(request, org_id: UUID, data: schemas.OrgSettingsSchema):
    from leagues.models import Organization
    org = get_object_or_404(Organization, id=org_id)

    if request.user.profile.role not in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
        return 403, {"message": "Unauthorized: Only organization admins can update settings."}

    org.max_events_per_team_per_week = data.max_events_per_team_per_week
    org.save()
    return 200, {"max_events_per_team_per_week": org.max_events_per_team_per_week}


@router.post("/games/{game_id}/start", response={200: schemas.GameSchema, 403: dict})
def start_game(request, game_id: UUID):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized: You do not have scoring permissions."}

    _init_scoring_data(game)
    game.is_live = True
    game.save()

    return {
        **game.__dict__,
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
    }


@router.post("/games/{game_id}/end", response={200: schemas.GameSchema, 403: dict})
def end_game(request, game_id: UUID, data: schemas.EndGameSchema):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized: You do not have scoring permissions."}

    if data and data.home_score is not None:
        game.home_score = data.home_score
    if data and data.away_score is not None:
        game.away_score = data.away_score

    game.is_completed = True
    game.save()

    return {
        **game.__dict__,
        "home_team_name": game.home_team.name,
        "away_team_name": game.away_team.name,
    }


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

    _apply_record_pitch(game, data.type, extra=getattr(data, 'extra', None))
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

    _apply_record_pitch(game, data.type, extra=getattr(data, 'extra', None))
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
@router.get("/organizations/{org_id}/youtube-config", response={200: schemas.OrganizationYouTubeConfigSchema, 404: dict})
def get_youtube_config(request, org_id: UUID):
    from leagues.models import Organization
    org = get_object_or_404(Organization, id=org_id)
    cfg = getattr(org, 'youtube_config', None)
    if not cfg:
        return 404, {"detail": "No config"}
    return schemas.OrganizationYouTubeConfigSchema(
        youtube_channel_id=cfg.youtube_channel_id,
        youtube_client_id=cfg.youtube_client_id,
        youtube_client_secret=cfg.youtube_client_secret,
        youtube_refresh_token=cfg.youtube_refresh_token,
        streaming_server_srt_url=cfg.streaming_server_srt_url,
        privacy_status=cfg.privacy_status,
        is_enabled=cfg.is_enabled,
    )

@router.put("/organizations/{org_id}/youtube-config", response=schemas.OrganizationYouTubeConfigSchema)
def update_youtube_config(request, org_id: UUID, data: schemas.OrganizationYouTubeConfigSchema):
    from leagues.models import Organization, OrganizationYouTubeConfig
    org = get_object_or_404(Organization, id=org_id)
    if not _can_manage_org(request, org.id):
        from ninja.errors import HttpError
        raise HttpError(403, "Permission denied")
    cfg, _ = OrganizationYouTubeConfig.objects.get_or_create(organization=org)
    cfg.youtube_channel_id = data.youtube_channel_id or ""
    cfg.youtube_client_id = data.youtube_client_id or ""
    cfg.youtube_client_secret = data.youtube_client_secret or ""
    cfg.youtube_refresh_token = data.youtube_refresh_token or ""
    cfg.streaming_server_srt_url = data.streaming_server_srt_url or ""
    cfg.privacy_status = data.privacy_status or "unlisted"
    cfg.is_enabled = data.is_enabled
    cfg.save()
    return schemas.OrganizationYouTubeConfigSchema(
        youtube_channel_id=cfg.youtube_channel_id,
        youtube_client_id=cfg.youtube_client_id,
        youtube_client_secret=cfg.youtube_client_secret,
        youtube_refresh_token=cfg.youtube_refresh_token,
        streaming_server_srt_url=cfg.streaming_server_srt_url,
        privacy_status=cfg.privacy_status,
        is_enabled=cfg.is_enabled,
    )


def _oauth_error_response(message, error_redirect):
    if error_redirect:
        from django.http import HttpResponseRedirect
        from urllib.parse import quote
        sep = '&' if '?' in error_redirect else '?'
        return HttpResponseRedirect(f"{error_redirect}{sep}error={quote(message)}")
    return 400, {'detail': message}


@router.get("/organizations/{org_id}/youtube/oauth/start", response={200: schemas.YouTubeOAuthStartSchema, 400: dict, 403: dict})
def youtube_oauth_start(request, org_id: UUID):
    from ninja.errors import HttpError
    from leagues.models import Organization
    org = get_object_or_404(Organization, id=org_id)
    if not _can_manage_org(request, org.id):
        raise HttpError(403, "Permission denied")
    try:
        url = oauth.build_authorization_url(org.id, request.user.id)
        redirect_uri = oauth.get_redirect_uri()
    except oauth.OAuthError as e:
        raise HttpError(400, str(e))
    return 200, schemas.YouTubeOAuthStartSchema(authorize_url=url, redirect_uri=redirect_uri)


@router.get("/youtube/oauth/callback", auth=None, response={200: schemas.YouTubeOAuthCallbackSchema, 400: dict, 404: dict})
def youtube_oauth_callback(request, code: str = None, state: str = None, error: str = None):
    from leagues.models import Organization, OrganizationYouTubeConfig
    success_redirect = getattr(settings, 'YOUTUBE_OAUTH_SUCCESS_REDIRECT', '')
    error_redirect = getattr(settings, 'YOUTUBE_OAUTH_ERROR_REDIRECT', '')
    if error:
        return _oauth_error_response(f"Authorization denied: {error}", error_redirect)
    try:
        payload = oauth.consume_state(state)
        tokens = oauth.exchange_code(code)
        org = Organization.objects.filter(id=payload['org_id']).first()
        if not org:
            raise oauth.OAuthError('Organization not found')
    except oauth.OAuthError as e:
        return _oauth_error_response(str(e), error_redirect)

    cfg, _ = OrganizationYouTubeConfig.objects.get_or_create(organization=org)
    cfg.youtube_client_id = tokens['client_id']
    cfg.youtube_client_secret = tokens['client_secret']
    cfg.youtube_refresh_token = tokens['refresh_token']
    cfg.youtube_channel_id = tokens['channel_id']
    cfg.is_enabled = True
    cfg.save(update_fields=[
        'youtube_client_id', 'youtube_client_secret', 'youtube_refresh_token',
        'youtube_channel_id', 'is_enabled', 'updated_at',
    ])

    if success_redirect:
        from django.http import HttpResponseRedirect
        sep = '&' if '?' in success_redirect else '?'
        return HttpResponseRedirect(
            f"{success_redirect}{sep}organization_id={org.id}&youtube_channel_id={cfg.youtube_channel_id}"
        )
    return 200, schemas.YouTubeOAuthCallbackSchema(
        connected=True,
        organization_id=str(org.id),
        youtube_channel_id=cfg.youtube_channel_id,
    )
