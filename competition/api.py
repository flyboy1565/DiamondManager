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


def _get_runners(game):
    return game.scoring_data.setdefault('runners', {'first': None, 'second': None, 'third': None})


def _set_runner(game, base, player_info):
    _get_runners(game)[base] = player_info


def _clear_runners(game):
    game.scoring_data['runners'] = {'first': None, 'second': None, 'third': None}


def _runner_at(game, base):
    return _get_runners(game).get(base)


def _make_runner_info(pid, pname=None):
    if not pid:
        return None
    if not pname:
        pname = _get_player_name(pid)
    return {'player_id': pid, 'player_name': pname}


def _advance_runners_on_hit(game, bases, current_batter):
    """
    Advance runners based on hit type (single=1, double=2, triple=3, homerun=4).
    Returns runs_scored and a list of movement descriptions.
    """
    runners = _get_runners(game)
    movements = []
    runs_scored = 0
    batter_name = current_batter.get('player_name', 'Batter')
    batter_id = current_batter.get('player_id')

    # Order: third → second → first (runners on furthest base score/advance first)
    base_order = ['third', 'second', 'first']
    base_map = {'first': 1, 'second': 2, 'third': 3}

    # Collect runners in order
    occupied = [(b, runners[b]) for b in base_order if runners[b]]

    new_runners = {'first': None, 'second': None, 'third': None}

    for base_name, info in occupied:
        target_base = base_map[base_name] + bases
        if target_base >= 4:
            runs_scored += 1
            movements.append(f"{info['player_name']} scores")
        else:
            target_name = {1: 'first', 2: 'second', 3: 'third'}[target_base]
            new_runners[target_name] = info
            movements.append(f"{info['player_name']} to {target_name}")

    # Batter
    if bases >= 4:
        runs_scored += 1
        movements.append(f"{batter_name} scores")
    else:
        target_name = {1: 'first', 2: 'second', 3: 'third'}[bases]
        new_runners[target_name] = _make_runner_info(batter_id, batter_name)
        movements.append(f"{batter_name} to {target_name}")

    game.scoring_data['runners'] = new_runners
    return runs_scored, movements


def _handle_walk(game, current_batter):
    """Handle a walk. Batter to 1st, forced runners advance. Returns (runs_scored, movements)."""
    runners = _get_runners(game)
    battery_id = current_batter.get('player_id')
    battery_name = current_batter.get('player_name', 'Batter')
    movements = []
    runs_scored = 0

    new_first = _make_runner_info(battery_id, battery_name)
    movements.append(f"{battery_name} draws a walk")

    if runners['first']:
        new_second = runners['first']
        movements.append(f"{runners['first']['player_name']} forced to second")
        if runners['second']:
            new_third = runners['second']
            movements.append(f"{runners['second']['player_name']} forced to third")
            if runners['third']:
                runs_scored = 1
                movements.append(f"{runners['third']['player_name']} scores")
            else:
                pass  # third was empty
        else:
            new_third = runners['third']
    else:
        new_second = runners['second']
        new_third = runners['third']

    game.scoring_data['runners'] = {'first': new_first, 'second': new_second, 'third': new_third}
    return runs_scored, movements


def _advance_inning(game):
    if game.is_top_inning:
        game.is_top_inning = False
    else:
        game.is_top_inning = True
        game.current_inning += 1
    game.outs = 0
    game.balls = 0
    game.strikes = 0
    _clear_runners(game)
    side = 'home' if not game.is_top_inning else 'away'
    _advance_batter(game, side)


def _reset_count(game):
    game.balls = 0
    game.strikes = 0


_HIT_BASES = {'single': 1, 'double': 2, 'triple': 3, 'homerun': 4}
_PITCH_LABELS = {
    'ball': 'Ball', 'ball_outside': 'Ball (outside)', 'ball_inside': 'Ball (inside)',
    'ball_high': 'Ball (high)', 'ball_low': 'Ball (low)', 'ball_dirt': 'Ball (in dirt)',
    'strike': 'Strike', 'strike_called': 'Strike (called)', 'strike_swinging': 'Strike (swinging)',
    'strike_foul_tip': 'Strike (foul tip)', 'foul': 'Foul',
    'single': 'Single', 'double': 'Double', 'triple': 'Triple', 'homerun': 'Home Run!',
    'out': 'Out', 'out_ground': 'Ground out', 'out_fly': 'Fly out',
    'out_line': 'Line out', 'out_pop': 'Pop out', 'strikeout': 'Strikeout',
    'hit': 'Hit', 'double_play': 'Double Play', 'pickoff': 'Pick Off',
    # New types
    'steal': 'Stolen Base', 'caught_stealing': 'Caught Stealing',
    'hit_by_pitch': 'Hit By Pitch',
    'sac_bunt': 'Sacrifice Bunt', 'sac_fly': 'Sacrifice Fly',
    'error': 'Error', 'fielders_choice': "Fielder's Choice",
    'wild_pitch': 'Wild Pitch', 'passed_ball': 'Passed Ball',
    'balk': 'Balk', 'dropped_third_strike': 'Dropped 3rd Strike',
    'infield_fly': 'Infield Fly', 'triple_play': 'Triple Play',
    'bunt': 'Bunt', 'bunt_foul': 'Foul Bunt',
}


def _describe_count(game):
    return f"{game.balls}-{game.strikes}"


def _make_pitch_description(game, pitch_type, runs_scored, movements, was_at_bat_end):
    """Build a human-readable play-by-play line for this pitch."""
    batter = game.scoring_data.get('current_batter', {}).get('player_name', 'Batter')
    label = _PITCH_LABELS.get(pitch_type, pitch_type)
    count_str = _describe_count(game)

    # Pickoffs are special — not an at-bat event but still significant
    if pitch_type == 'pickoff':
        return " · ".join(movements) if movements else f"{label} attempt"

    # At-bat-ending events get the full description
    if was_at_bat_end:
        parts = [f"{batter} — {label}"]
        if movements:
            for m in movements[:3]:
                parts.append(m)
        if runs_scored > 0:
            parts.append(f"+{runs_scored} run{'s' if runs_scored > 1 else ''}")
        return " · ".join(parts)
    else:
        return f"{label} ({count_str})"


def _infield_fly_applies(game):
    """Check if infield fly rule is in effect: < 2 outs, runners on 1st AND 2nd (or bases loaded)."""
    if game.outs >= 2:
        return False
    runners = _get_runners(game)
    return runners.get('first') and runners.get('second')


def _handle_steal(game, runner_base, success=True, caught_base=None):
    """
    Handle a steal attempt.
    runner_base: which base the runner is on ('first', 'second', 'third')
    success: True for successful steal, False for caught stealing
    caught_base: if caught, which base they were out at (usually the next one)
    Returns (runs_scored, movements, side_retired).
    """
    runners = _get_runners(game)
    base_order = {'first': 1, 'second': 2, 'third': 3}
    target_map = {1: 'first', 2: 'second', 3: 'third'}
    movements = []
    runs_scored = 0
    side_retired = False

    if not runners.get(runner_base):
        return 0, ["No runner on base"], False

    info = runners[runner_base]
    base_num = base_order[runner_base]
    target_num = base_num + 1

    if success:
        if target_num >= 4:
            runs_scored = 1
            runners[runner_base] = None
            movements.append(f"{info['player_name']} steals home — scores!")
        else:
            target_base = target_map[target_num]
            if runners.get(target_base):
                movements.append(f"{info['player_name']} holds at {runner_base}")
            else:
                runners[runner_base] = None
                runners[target_base] = info
                movements.append(f"{info['player_name']} steals {target_base}")
        game.scoring_data['runners'] = runners
    else:
        # Caught stealing
        out_base = caught_base or target_map.get(target_num, runner_base)
        runners[runner_base] = None
        game.outs += 1
        movements.append(f"{info['player_name']} caught stealing {out_base}")
        if game.outs >= 3:
            _clear_runners(game)
            _advance_inning(game)
            movements.append("Side retired")
            side_retired = True

    return runs_scored, movements, side_retired


def _handle_hit_by_pitch(game, current_batter):
    """Batter hit by pitch. Goes to 1st, force runners. No count change, no AB."""
    movements = []
    runs_scored = 0
    runners = _get_runners(game)
    batter_name = current_batter.get('player_name', 'Batter')
    batter_id = current_batter.get('player_id')

    movements.append(f"{batter_name} hit by pitch")
    new_first = _make_runner_info(batter_id, batter_name)

    # Force advancement
    old_first = runners.get('first')
    old_second = runners.get('second')
    old_third = runners.get('third')

    # Third forced home if bases loaded
    if old_third and old_second and old_first:
        runs_scored = 1
        movements.append(f"{old_third['player_name']} forced home")
        runners['third'] = old_second
        runners['second'] = old_first
        runners['first'] = new_first
    elif old_second and old_first:
        runners['third'] = old_second
        runners['second'] = old_first
        runners['first'] = new_first
        movements.append(f"{old_second['player_name']} forced to third")
        movements.append(f"{old_first['player_name']} forced to second")
    elif old_first:
        runners['second'] = old_first
        runners['first'] = new_first
        movements.append(f"{old_first['player_name']} forced to second")
    else:
        runners['first'] = new_first

    game.scoring_data['runners'] = runners
    return runs_scored, movements


def _handle_sacrifice(game, current_batter, sac_type='bunt'):
    """
    Handle sacrifice bunt or fly. Batter is out, runners advance.
    sac_type: 'bunt' or 'fly'
    Returns (runs_scored, movements, side_retired).
    """
    movements = []
    runs_scored = 0
    runners = _get_runners(game)
    batter_name = current_batter.get('player_name', 'Batter')
    side_retired = False

    game.outs += 1
    label = "Sacrifice bunt" if sac_type == 'bunt' else "Sacrifice fly"
    movements.append(f"{batter_name} — {label}")

    if sac_type == 'bunt':
        if runners.get('second') and not runners.get('third'):
            runners['third'] = runners['second']
            runners['second'] = None
            movements.append(f"{runners['third']['player_name']} to third")
        if runners.get('first') and not runners.get('second'):
            runners['second'] = runners['first']
            runners['first'] = None
            movements.append(f"{runners['second']['player_name']} to second")
    elif sac_type == 'fly':
        if runners.get('third'):
            runs_scored = 1
            movements.append(f"{runners['third']['player_name']} scores")
            runners['third'] = None

    game.scoring_data['runners'] = runners

    if game.outs >= 3:
        _clear_runners(game)
        _advance_inning(game)
        movements.append("Side retired")
        side_retired = True

    return runs_scored, movements, side_retired


def _handle_error(game, current_batter):
    """
    Batter reaches safely on an error. No AB charged, no hit.
    Runners may advance one base.
    Returns (runs_scored, movements).
    """
    movements = []
    runs_scored = 0
    runners = _get_runners(game)
    batter_name = current_batter.get('player_name', 'Batter')
    batter_id = current_batter.get('player_id')

    movements.append(f"{batter_name} reaches on error")

    new_batter = _make_runner_info(batter_id, batter_name)
    old_first = runners.get('first')
    old_second = runners.get('second')
    old_third = runners.get('third')

    if old_first:
        if old_second:
            if old_third:
                runs_scored = 1
                movements.append(f"{old_third['player_name']} scores")
            else:
                runners['third'] = old_second
            runners['second'] = old_first
        else:
            runners['second'] = old_first
    runners['first'] = new_batter

    game.scoring_data['runners'] = runners
    return runs_scored, movements


def _handle_wild_or_passed_ball(game, is_passed_ball=False):
    """
    Handle wild pitch or passed ball — all runners advance one base.
    No batter effect.
    Returns (runs_scored, movements).
    """
    movements = []
    runs_scored = 0
    runners = _get_runners(game)
    label = "Passed ball" if is_passed_ball else "Wild pitch"

    if runners.get('third'):
        runs_scored += 1
        movements.append(f"{runners['third']['player_name']} scores on {label}")
        runners['third'] = None
    if runners.get('second'):
        if not runners.get('third'):
            runners['third'] = runners['second']
            runners['second'] = None
            movements.append(f"{runners['third']['player_name']} to third on {label}")
    if runners.get('first'):
        if not runners.get('second'):
            runners['second'] = runners['first']
            runners['first'] = None
            movements.append(f"{runners['second']['player_name']} to second on {label}")

    game.scoring_data['runners'] = runners
    return runs_scored, movements


def _handle_balk(game):
    """
    Balk — all runners advance one base. Batter unaffected.
    Returns (runs_scored, movements).
    """
    movements = []
    runs_scored = 0
    runners = _get_runners(game)

    movements.append("Balk")

    if runners.get('third'):
        runs_scored += 1
        movements.append(f"{runners['third']['player_name']} scores on balk")
        runners['third'] = None
    if runners.get('second'):
        if not runners.get('third'):
            runners['third'] = runners['second']
            movements.append(f"{runners['second']['player_name']} advances on balk")
        runners['second'] = None
    if runners.get('first'):
        if not runners.get('second'):
            runners['second'] = runners['first']
            movements.append(f"{runners['first']['player_name']} advances on balk")
        runners['first'] = None

    game.scoring_data['runners'] = runners
    return runs_scored, movements


def _handle_dropped_third_strike(game, current_batter):
    """
    Dropped 3rd strike — batter can attempt to reach 1st safely.
    Only applies if 1st base is unoccupied OR there are 2 outs.
    Returns (runs_scored, movements, batter_safe, side_retired).
    """
    movements = []
    runs_scored = 0
    runners = _get_runners(game)
    batter_name = current_batter.get('player_name', 'Batter')
    batter_id = current_batter.get('player_id')
    side_retired = False

    can_run = not runners.get('first') or game.outs >= 2
    if can_run:
        movement_text = f"{batter_name} reaches on dropped 3rd strike"
        new_batter = _make_runner_info(batter_id, batter_name)
        old_first = runners.get('first')
        old_second = runners.get('second')
        old_third = runners.get('third')

        if old_third and old_second and old_first:
            runs_scored = 1
            movements.append(f"{old_third['player_name']} forced home")
            runners['third'] = old_second
            runners['second'] = old_first
            runners['first'] = new_batter
        elif old_second and old_first:
            runners['third'] = old_second
            runners['second'] = old_first
            runners['first'] = new_batter
        elif old_first:
            runners['second'] = old_first
            runners['first'] = new_batter
        else:
            runners['first'] = new_batter
        movements.append(movement_text)
        game.scoring_data['runners'] = runners
        return runs_scored, movements, True, False  # batter safe
    else:
        game.outs += 1
        movements.append(f"{batter_name} strikes out (dropped, thrown out)")
        if game.outs >= 3:
            _clear_runners(game)
            _advance_inning(game)
            movements.append("Side retired")
            side_retired = True
        return 0, movements, False, side_retired  # batter out


def _apply_record_pitch(game, pitch_type, extra=None):
    # Capture state before any mutations (pitch happened in this inning)
    recorded_inning = game.current_inning
    recorded_is_top = game.is_top_inning
    snapshot = {
        'balls': game.balls,
        'strikes': game.strikes,
        'outs': game.outs,
        'home': game.home_score,
        'away': game.away_score,
    }
    runners_before = dict(_get_runners(game))

    side = 'home' if not game.is_top_inning else 'away'
    batter_side = 'away' if game.is_top_inning else 'home'

    current_batter = game.scoring_data.get('current_batter', {})
    current_pitcher = game.scoring_data.get('current_pitcher', {}).get(side, {})

    was_at_bat_end = False
    runs_scored = 0
    movements = []
    scoring_side = 'home' if batter_side == 'home' else 'away'

    # Ball variants
    if pitch_type in ('ball', 'ball_outside', 'ball_inside', 'ball_high', 'ball_low', 'ball_dirt'):
        game.balls += 1
        if game.balls >= 4:
            game.balls = 0
            game.strikes = 0
            was_at_bat_end = True
            runs_scored, movements = _handle_walk(game, current_batter)
            if runs_scored:
                if scoring_side == 'home':
                    game.home_score += runs_scored
                else:
                    game.away_score += runs_scored
            _advance_batter(game, side)

    # Strike variants
    elif pitch_type in ('strike', 'strike_called', 'strike_swinging', 'strike_foul_tip'):
        game.strikes += 1
        if game.strikes >= 3:
            was_at_bat_end = True
            game.outs += 1
            _reset_count(game)
            batter_name = current_batter.get('player_name', 'Batter')
            movements.append(f"{batter_name} strikes out")
            if game.outs >= 3:
                _clear_runners(game)
                _advance_inning(game)
                movements.append("Side retired")
            else:
                _advance_batter(game, side)

    elif pitch_type == 'foul':
        if game.strikes < 2:
            game.strikes += 1

    # Safe hits (batter reached base, no out)
    elif pitch_type in ('single', 'double', 'triple', 'homerun'):
        was_at_bat_end = True
        bases = _HIT_BASES.get(pitch_type, 1)
        runs_scored, movements = _advance_runners_on_hit(game, bases, current_batter)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored
        # Batter also might have scored via homerun — handled inside _advance_runners_on_hit
        # But homerun scoring was counted already in _advance_runners_on_hit (bases=4 → batter scores)
        _reset_count(game)
        _advance_batter(game, side)

    # Out variants
    elif pitch_type in ('hit', 'out', 'out_ground', 'out_fly', 'out_line', 'out_pop', 'strikeout'):
        was_at_bat_end = True
        game.outs += 1
        _reset_count(game)
        batter_name = current_batter.get('player_name', 'Batter')
        label = _PITCH_LABELS.get(pitch_type, 'Out')
        movements.append(f"{batter_name} — {label}")
        if game.outs >= 3:
            _clear_runners(game)
            _advance_inning(game)
            movements.append("Side retired")
        else:
            _advance_batter(game, side)

    # Double play / Triple play — batter out + lead runner(s) out
    elif pitch_type in ('double_play', 'triple_play'):
        was_at_bat_end = True
        extra = extra or {}
        batter_name = current_batter.get('player_name', 'Batter')
        runners = _get_runners(game)
        label = 'Triple Play' if pitch_type == 'triple_play' else 'Double Play'
        outs_to_record = 3 if pitch_type == 'triple_play' else 2

        # If extra specifies which runners/outs, use that
        outs_recorded = extra.get('outs', [])
        if outs_recorded:
            for out_info in outs_recorded[:outs_to_record]:
                out_base = out_info.get('base')
                out_player = out_info.get('player_name', '')
                if out_base == 'batter':
                    movements.append(f"{out_player} — {label}")
                else:
                    movements.append(f"{out_player} out at {out_base}")
                    if runners.get(out_base):
                        runners[out_base] = None
                game.outs += 1
        else:
            # Default: remove lead runner(s) + batter
            for _ in range(outs_to_record - 1):
                for b in ('third', 'second', 'first'):
                    if runners[b]:
                        lead_name = runners[b]['player_name']
                        runners[b] = None
                        movements.append(f"{lead_name} out on the {label}")
                        game.outs += 1
                        break
            # Batter is also out
            game.outs += 1 if outs_to_record == 3 else 1
            movements.append(f"{batter_name} — {label}")

        _reset_count(game)
        if game.outs >= 3:
            _clear_runners(game)
            _advance_inning(game)
            movements.append("Side retired")
        else:
            _advance_batter(game, side)

    # Pick off — pitcher catches a runner off base (with runner selection)
    elif pitch_type == 'pickoff':
        was_at_bat_end = False
        extra = extra or {}
        runners = _get_runners(game)
        # Use specified runner base, or default to furthest
        picked_base = extra.get('runner_base')
        if not picked_base:
            for b in ('third', 'second', 'first'):
                if runners[b]:
                    picked_base = b
                    break
        if picked_base and runners.get(picked_base):
            picked_name = runners[picked_base]['player_name']
            runners[picked_base] = None
            game.outs += 1
            movements.append(f"{picked_name} picked off {picked_base}")
            if game.outs >= 3:
                _clear_runners(game)
                _advance_inning(game)
                movements.append("Side retired")
        else:
            movements.append("Pick off attempt — no runners")

    # Steal — successful stolen base
    elif pitch_type == 'steal':
        was_at_bat_end = False
        extra = extra or {}
        runner_base = extra.get('runner_base', 'first')
        runs, mov, _ = _handle_steal(game, runner_base, success=True)
        runs_scored += runs
        movements.extend(mov)
        if runs_scored and scoring_side == 'home':
            game.home_score += runs_scored
        elif runs_scored:
            game.away_score += runs_scored

    # Caught stealing
    elif pitch_type == 'caught_stealing':
        was_at_bat_end = False
        extra = extra or {}
        runner_base = extra.get('runner_base', 'first')
        caught_base = extra.get('caught_base')
        runs, mov, side_retired = _handle_steal(game, runner_base, success=False, caught_base=caught_base)
        runs_scored += runs
        movements.extend(mov)

    # Hit by pitch
    elif pitch_type == 'hit_by_pitch':
        was_at_bat_end = True
        _reset_count(game)
        runs, mov = _handle_hit_by_pitch(game, current_batter)
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored
        _advance_batter(game, side)

    # Sacrifice bunt
    elif pitch_type == 'sac_bunt':
        was_at_bat_end = True
        _reset_count(game)
        runs, mov, side_retired = _handle_sacrifice(game, current_batter, sac_type='bunt')
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored
        if not side_retired:
            _advance_batter(game, side)

    # Sacrifice fly
    elif pitch_type == 'sac_fly':
        was_at_bat_end = True
        _reset_count(game)
        runs, mov, side_retired = _handle_sacrifice(game, current_batter, sac_type='fly')
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored
        if not side_retired:
            _advance_batter(game, side)

    # Error — batter safe, no AB
    elif pitch_type == 'error':
        was_at_bat_end = True
        _reset_count(game)
        runs, mov = _handle_error(game, current_batter)
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored
        _advance_batter(game, side)

    # Fielder's choice — lead runner out, batter safe
    elif pitch_type == 'fielders_choice':
        was_at_bat_end = True
        _reset_count(game)
        runners = _get_runners(game)
        fc_runner_base = extra.get('runner_base') if extra else None
        movements.append(f"{current_batter.get('player_name', 'Batter')} reaches on fielder's choice")
        # Lead runner out
        if fc_runner_base and runners.get(fc_runner_base):
            out_name = runners[fc_runner_base]['player_name']
            runners[fc_runner_base] = None
            game.outs += 1
            movements.append(f"{out_name} out on fielder's choice")
        else:
            # Default: put out the lead runner
            for b in ('third', 'second', 'first'):
                if runners[b]:
                    out_name = runners[b]['player_name']
                    runners[b] = None
                    game.outs += 1
                    movements.append(f"{out_name} out on fielder's choice")
                    break
        # Batter safe at 1st
        batter_info = _make_runner_info(
            current_batter.get('player_id'),
            current_batter.get('player_name')
        )
        if runners.get('first'):
            # Force advance remaining runners
            old_first = runners['first']
            old_second = runners.get('second')
            if old_second:
                runners['third'] = runners.get('third') or old_second
            runners['second'] = old_first
        runners['first'] = batter_info
        game.scoring_data['runners'] = runners
        if game.outs >= 3:
            _clear_runners(game)
            _advance_inning(game)
            movements.append("Side retired")
        else:
            _advance_batter(game, side)

    # Wild pitch / Passed ball
    elif pitch_type in ('wild_pitch', 'passed_ball'):
        was_at_bat_end = False
        is_pb = (pitch_type == 'passed_ball')
        runs, mov = _handle_wild_or_passed_ball(game, is_passed_ball=is_pb)
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored

    # Balk
    elif pitch_type == 'balk':
        was_at_bat_end = False
        runs, mov = _handle_balk(game)
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored

    # Dropped 3rd strike
    elif pitch_type == 'dropped_third_strike':
        was_at_bat_end = True
        game.strikes = 0
        game.balls = 0
        runs, mov, batter_safe, side_retired = _handle_dropped_third_strike(game, current_batter)
        runs_scored += runs
        movements.extend(mov)
        if runs_scored:
            if scoring_side == 'home':
                game.home_score += runs_scored
            else:
                game.away_score += runs_scored
        if not side_retired:
            _advance_batter(game, side)
        elif not batter_safe and game.outs < 3:
            _advance_batter(game, side)

    # Infield fly — automatic out, runners hold (but may advance at own risk)
    elif pitch_type == 'infield_fly':
        was_at_bat_end = True
        game.outs += 1
        _reset_count(game)
        batter_name = current_batter.get('player_name', 'Batter')
        movements.append(f"{batter_name} — Infield Fly (automatic out)")
        if game.outs >= 3:
            _clear_runners(game)
            _advance_inning(game)
            movements.append("Side retired")
        else:
            _advance_batter(game, side)

    # Bunt (regular, not sacrifice — batter attempts to bunt for a hit)
    elif pitch_type == 'bunt':
        was_at_bat_end = True
        extras = extra or {}
        result = extras.get('bunt_result', 'out_ground')
        if result in ('single',):
            # Bunt single
            game.balls = 0
            game.strikes = 0
            runs, mov = _advance_runners_on_hit(game, 1, current_batter)
            runs_scored += runs
            movements.extend(mov)
            movements.append(f"{current_batter.get('player_name', 'Batter')} bunt single")
            if runs_scored:
                if scoring_side == 'home':
                    game.home_score += runs_scored
                else:
                    game.away_score += runs_scored
            _advance_batter(game, side)
        else:
            # Bunt out
            game.outs += 1
            _reset_count(game)
            movements.append(f"{current_batter.get('player_name', 'Batter')} bunt out")
            if game.outs >= 3:
                _clear_runners(game)
                _advance_inning(game)
                movements.append("Side retired")
            else:
                _advance_batter(game, side)

    # Foul bunt with 2 strikes = strikeout
    elif pitch_type == 'bunt_foul':
        game.strikes += 1
        if game.strikes >= 3:
            was_at_bat_end = True
            game.outs += 1
            _reset_count(game)
            movements.append(f"{current_batter.get('player_name', 'Batter')} strikes out (foul bunt)")
            if game.outs >= 3:
                _clear_runners(game)
                _advance_inning(game)
                movements.append("Side retired")
            else:
                _advance_batter(game, side)

    game.pitch_count += 1
    description = _make_pitch_description(game, pitch_type, runs_scored, movements, was_at_bat_end)
    runners_after = dict(_get_runners(game))

    pitch_record = {
        'id': len(game.scoring_data.get('pitches', [])) + 1,
        'inning': recorded_inning,
        'is_top': recorded_is_top,
        'result': {'type': pitch_type},
        'before': snapshot,
        'batter': {
            'player_id': current_batter.get('player_id'),
            'player_name': current_batter.get('player_name'),
        },
        'pitcher': {
            'player_id': current_pitcher.get('player_id'),
            'player_name': current_pitcher.get('player_name'),
        },
        'description': description,
        'runners_before': runners_before,
        'runners_after': runners_after,
        'runs_scored': runs_scored,
        'was_at_bat_end': was_at_bat_end,
        'timestamp': timezone.now().isoformat(),
        'extra': extra or {},
    }
    game.scoring_data.setdefault('pitches', []).append(pitch_record)


def compute_game_stats(game):
    """Derive per-batter, per-pitcher, and per-inning stats from pitch data."""
    pitches = game.scoring_data.get('pitches', [])

    batters = {}
    pitchers = {}
    innings_data = {}
    prev_home = 0
    prev_away = 0
    current_inning = None

    for pitch in pitches:
        inning = pitch.get('inning', 1)
        is_top = pitch.get('is_top', True)
        side = 'away' if is_top else 'home'
        result = pitch.get('result', {}).get('type', '')
        before = pitch.get('before', {})
        b_balls = before.get('balls', 0)
        b_strikes = before.get('strikes', 0)

        # Track inning boundaries for runs
        if current_inning is None or inning != current_inning:
            if current_inning is not None:
                # Close out previous inning
                innings_data[current_inning] = {
                    'home': before.get('home', 0) - prev_home,
                    'away': before.get('away', 0) - prev_away,
                }
            prev_home = before.get('home', 0)
            prev_away = before.get('away', 0)
            current_inning = inning

        # Batter stats
        batter = pitch.get('batter', {})
        batter_id = batter.get('player_id')
        if batter_id:
            if batter_id not in batters:
                batters[batter_id] = {
                    'name': batter.get('player_name', 'Unknown'),
                    'ab': 0, 'hits': 0, 'strikeouts': 0, 'walks': 0, 'pitches_seen': 0,
                    'hbp': 0, 'sac': 0, 'error': 0, 'fc': 0, 'sb': 0, 'cs': 0,
                }
            batters[batter_id]['pitches_seen'] += 1

            if result in ('single', 'double', 'triple', 'homerun'):
                batters[batter_id]['hits'] += 1
                batters[batter_id]['ab'] += 1
            elif result in ('strikeout', 'out', 'out_ground', 'out_fly', 'out_line', 'out_pop'):
                batters[batter_id]['ab'] += 1
                if result == 'strikeout':
                    batters[batter_id]['strikeouts'] += 1
            elif result == 'hit':
                batters[batter_id]['ab'] += 1
            elif result in ('double_play', 'triple_play'):
                batters[batter_id]['ab'] += 1
            elif result == 'infield_fly':
                batters[batter_id]['ab'] += 1
            elif result == 'fielders_choice':
                batters[batter_id]['ab'] += 1  # FC counts as AB, no hit
            elif result == 'error':
                batters[batter_id]['error'] += 1  # No AB charged
            elif result in ('sac_bunt', 'sac_fly'):
                batters[batter_id]['sac'] += 1  # No AB charged
            elif result == 'hit_by_pitch':
                batters[batter_id]['hbp'] += 1  # No AB charged
            elif result == 'bunt':
                batter_bunt_result = pitch.get('extra', {}).get('bunt_result', 'out_ground')
                if batter_bunt_result == 'single':
                    batters[batter_id]['hits'] += 1
                    batters[batter_id]['ab'] += 1
                else:
                    batters[batter_id]['ab'] += 1
            elif result == 'dropped_third_strike':
                batters[batter_id]['ab'] += 0  # No AB on dropped 3rd strike
                batters[batter_id]['strikeouts'] += 1  # Still a K in the books
            elif 'ball' in result and b_balls == 3:
                batters[batter_id]['walks'] += 1

        # Pitcher stats
        pitcher = pitch.get('pitcher', {})
        pitcher_id = pitcher.get('player_id')
        if pitcher_id:
            if pitcher_id not in pitchers:
                pitchers[pitcher_id] = {
                    'name': pitcher.get('player_name', 'Unknown'),
                    'pitch_count': 0, 'strikeouts': 0, 'hits_allowed': 0, 'walks_allowed': 0,
                    'hbp': 0, 'wp': 0, 'bk': 0, 'sb_allowed': 0, 'cs': 0,
                }
            pitchers[pitcher_id]['pitch_count'] += 1
            if result in ('single', 'double', 'triple', 'homerun'):
                pitchers[pitcher_id]['hits_allowed'] += 1
            elif result == 'strikeout':
                pitchers[pitcher_id]['strikeouts'] += 1
            elif result in ('pickoff', 'caught_stealing'):
                pitchers[pitcher_id]['cs'] += 1
            elif result == 'hit_by_pitch':
                pitchers[pitcher_id]['hbp'] += 1
            elif result == 'wild_pitch':
                pitchers[pitcher_id]['wp'] += 1
            elif result == 'balk':
                pitchers[pitcher_id]['bk'] += 1
            elif result == 'steal':
                pitchers[pitcher_id]['sb_allowed'] += 1
            elif 'ball' in result and b_balls == 3:
                pitchers[pitcher_id]['walks_allowed'] += 1

    # Close out the last inning with final score
    if current_inning is not None and current_inning not in innings_data:
        innings_data[current_inning] = {
            'home': game.home_score - prev_home,
            'away': game.away_score - prev_away,
        }

    # Compute AVG for batters who have ABs
    for b in batters.values():
        b['avg'] = f"{b['hits'] / b['ab']:.3f}" if b['ab'] > 0 else '.---'

    return {
        'batters': batters,
        'pitchers': pitchers,
        'innings': innings_data,
    }


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
    entries = game.lineup_entries.select_related('team__division', 'player').all()
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
            "division_id": entry.team.division_id,
        }
        for entry in entries
    ]


@router.post("/games/{game_id}/lineup/entries", response={201: schemas.LineupEntrySchema, 403: dict})
def create_lineup_entry(request, game_id: UUID, data: schemas.LineupEntryCreateSchema):
    game = get_object_or_404(Game, id=game_id)
    from .models import GameLineupEntry
    from profiles.models import Player
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized."}
    player = get_object_or_404(Player, id=data.player_id)
    entry = GameLineupEntry.objects.create(
        game=game,
        team_id=data.team_id,
        player=player,
        batting_order=data.batting_order,
        position=data.position or "",
    )
    return 201, {
        "id": entry.id,
        "team_id": entry.team_id,
        "team_name": entry.team.name,
        "player_id": entry.player_id,
        "player_name": f"{entry.player.first_name} {entry.player.last_name}",
        "batting_order": entry.batting_order,
        "position": entry.position,
        "is_active": entry.is_active,
        "division_id": entry.team.division_id,
    }

@router.put("/games/{game_id}/lineup/entries/{entry_id}", response=schemas.LineupEntrySchema)
def update_lineup_entry(request, game_id: UUID, entry_id: int, data: schemas.LineupEntryUpdateSchema):
    game = get_object_or_404(Game, id=game_id)
    from .models import GameLineupEntry
    entry = get_object_or_404(GameLineupEntry, id=entry_id, game=game)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(entry, attr, value)
    entry.save()
    return {
        "id": entry.id,
        "team_id": entry.team_id,
        "team_name": entry.team.name,
        "player_id": entry.player_id,
        "player_name": f"{entry.player.first_name} {entry.player.last_name}",
        "batting_order": entry.batting_order,
        "position": entry.position,
        "is_active": entry.is_active,
        "division_id": entry.team.division_id,
    }

@router.delete("/games/{game_id}/lineup/entries/{entry_id}", response=dict)
def delete_lineup_entry(request, game_id: UUID, entry_id: int):
    game = get_object_or_404(Game, id=game_id)
    from .models import GameLineupEntry
    entry = get_object_or_404(GameLineupEntry, id=entry_id, game=game)
    entry.delete()
    return {"success": True}

@router.post("/games/{game_id}/lineup/clone", response={201: List[schemas.LineupEntrySchema], 403: dict, 404: dict})
def clone_lineup(request, game_id: UUID, data: schemas.CloneLineupSchema):
    game = get_object_or_404(Game, id=game_id)
    if not _can_score(request, game):
        return 403, {"message": "Unauthorized."}

    source_game = get_object_or_404(Game, id=data.source_game_id)
    from .models import GameLineupEntry

    source_entries = GameLineupEntry.objects.filter(game=source_game).select_related('team', 'player')
    if not source_entries.exists():
        return 404, {"message": "Source game has no lineup entries."}

    cloned = []
    for se in source_entries:
        new_entry, _ = GameLineupEntry.objects.update_or_create(
            game=game,
            team=se.team,
            player=se.player,
            defaults={
                "batting_order": se.batting_order,
                "position": se.position,
                "is_active": se.is_active,
            }
        )
        cloned.append(new_entry)
    return 201, [
        {
            "id": e.id,
            "team_id": e.team_id,
            "team_name": e.team.name,
            "player_id": e.player_id,
            "player_name": f"{e.player.first_name} {e.player.last_name}",
            "batting_order": e.batting_order,
            "position": e.position,
            "is_active": e.is_active,
            "division_id": e.team.division_id,
        }
        for e in cloned
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