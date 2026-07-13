from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView, View, FormView
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from leagues.models import Team, Division, Organization, Season
from .models import TeamEvent, Game, GameLineupEntry
from .forms import TeamEventForm, GameScoreForm, DivisionEventForm, OrganizationEventForm, LineupEntryForm, ScheduleGameForm, DEFENSIVE_POSITION_CHOICES
from .permissions import can_create_event, can_edit_event, get_allowed_event_types
from .scheduling import get_week_range, team_event_count, team_can_add_events, get_location_conflicts
from profiles.models import PlayerMembership, TeamMembership, Player


def _build_extra_from_post(post_data, pitch_type):
    """Extract extra parameters from POST data for complex pitch types."""
    extra = {}
    if pitch_type in ('steal', 'caught_stealing', 'pickoff', 'fielders_choice'):
        runner_base = post_data.get('runner_base')
        if runner_base:
            extra['runner_base'] = runner_base
    if pitch_type == 'caught_stealing':
        caught_base = post_data.get('caught_base')
        if caught_base:
            extra['caught_base'] = caught_base
    if pitch_type in ('double_play', 'triple_play'):
        import json
        outs_raw = post_data.get('dp_outs')
        if outs_raw:
            try:
                extra['outs'] = json.loads(outs_raw)
            except (json.JSONDecodeError, TypeError):
                pass
    if pitch_type == 'bunt':
        bunt_result = post_data.get('bunt_result')
        if bunt_result:
            extra['bunt_result'] = bunt_result
    return extra


class TeamEventsListView(LoginRequiredMixin, ListView):
    """
    Display all events for a team in calendar/list format.
    """
    model = TeamEvent
    template_name = 'competition/team_events.html'
    context_object_name = 'events'
    paginate_by = 20
    
    def get_queryset(self):
        team_id = self.kwargs.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        queryset = TeamEvent.objects.filter(team=team).order_by('date_time')
        
        # Filter by status if provided
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by event type if provided
        event_type = self.request.GET.get('type')
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team_id = self.kwargs.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        context['team'] = team
        context['allowed_event_types'] = get_allowed_event_types(self.request.user, 'TEAM', team=team)
        # Provide event types for filters (team-scoped)
        context['event_types'] = [c for c in TeamEvent.EVENT_TYPE_CHOICES if 'TEAM' in c[0]]
        # Can the current user create events for this team?
        profile = self.request.user.profile
        if profile.role in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
            context['can_create'] = True
        else:
            from profiles.models import TeamMembership
            context['can_create'] = TeamMembership.objects.filter(
                user=self.request.user, team=team,
                role__in=['MANAGER', 'COACH'], is_active=True
            ).exists() and bool(context['allowed_event_types'])
        return context


class CreateTeamEventView(LoginRequiredMixin, CreateView):
    """
    Create a new team event with permission checks.
    """
    model = TeamEvent
    form_class = TeamEventForm
    template_name = 'competition/create_event.html'

    def get(self, request, *args, **kwargs):
        team_id = self.kwargs.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        profile = request.user.profile
        if profile.role not in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
            from profiles.models import TeamMembership
            if not TeamMembership.objects.filter(
                user=request.user, team=team,
                role__in=['MANAGER', 'COACH'], is_active=True
            ).exists():
                messages.error(request, "You don't have permission to create events for this team.")
                return redirect('team_events', team_id=team_id)
        return super().get(request, *args, **kwargs)
    
    def get_initial(self):
        initial = super().get_initial()
        team_id = self.kwargs.get('team_id')
        initial['team'] = get_object_or_404(Team, id=team_id)
        return initial
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        team_id = self.kwargs.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        allowed_types = get_allowed_event_types(self.request.user, 'TEAM', team=team)
        kwargs['team'] = team
        kwargs['allowed_event_types'] = allowed_types
        return kwargs
    
    def form_valid(self, form):
        team_id = self.kwargs.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        event_type = form.cleaned_data.get('event_type')
        
        # Check permissions
        if not can_create_event(self.request.user, 'TEAM', event_type, team=team):
            messages.error(self.request, f"You don't have permission to create {event_type} events.")
            return redirect('team_events', team_id=team_id)
        
        # Check weekly event limit
        if getattr(form.instance, 'counts_against_limit', True):
            allowed, current, max_allowed = team_can_add_events(team)
            if not allowed:
                messages.error(
                    self.request,
                    f"{team.name} has {current}/{max_allowed} events this week — cannot schedule more."
                )
                return redirect('team_events', team_id=team_id)
        
        # Set creator and team
        form.instance.team = team
        form.instance.created_by = self.request.user
        
        messages.success(self.request, f"Event '{form.cleaned_data.get('title')}' created successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        team_id = self.kwargs.get('team_id')
        return f'/competitions/team/{team_id}/events/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team_id = self.kwargs.get('team_id')
        context['team'] = get_object_or_404(Team, id=team_id)
        return context


class EditTeamEventView(LoginRequiredMixin, UpdateView):
    """
    Edit an existing team event with permission checks.
    """
    model = TeamEvent
    form_class = TeamEventForm
    template_name = 'competition/edit_event.html'
    pk_url_kwarg = 'event_id'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        event = self.get_object()
        allowed_types = get_allowed_event_types(self.request.user, 'TEAM', team=event.team)
        kwargs['team'] = event.team
        kwargs['allowed_event_types'] = allowed_types
        return kwargs
    
    def get(self, request, *args, **kwargs):
        event = self.get_object()
        if not can_edit_event(request.user, event):
            messages.error(request, "You don't have permission to edit this event.")
            return redirect('team_events', team_id=event.team.id)
        return super().get(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f"Event updated successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        event = self.get_object()
        return f'/competitions/team/{event.team.id}/events/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.get_object()
        context['team'] = event.team
        return context


class EventDetailView(LoginRequiredMixin, DetailView):
    """
    Display event details with option to record scores for games.
    """
    model = TeamEvent
    template_name = 'competition/event_detail.html'
    pk_url_kwarg = 'event_id'
    context_object_name = 'event'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.get_object()
        context['team'] = event.team
        context['can_edit'] = can_edit_event(self.request.user, event)
        
        # Show score form for game/scrimmage events (legacy Game or new TEAM_* types)
        if 'GAME' in event.event_type or 'SCRIMMAGE' in event.event_type:
            context['score_form'] = GameScoreForm()
        
        return context
    
    def post(self, request, *args, **kwargs):
        event = self.get_object()
        
        if not can_edit_event(request.user, event):
            messages.error(request, "You don't have permission to update this event.")
            return redirect('event_detail', event_id=event.id)
        
        if event.event_type in ['GAME', 'SCRIMMAGE']:
            form = GameScoreForm(request.POST)
            if form.is_valid():
                event.home_score = form.cleaned_data['home_score']
                event.away_score = form.cleaned_data['away_score']
                event.status = 'COMPLETED'
                event.save()
                messages.success(request, "Score recorded successfully.")
                return redirect('event_detail', event_id=event.id)
        
        return self.get(request, *args, **kwargs)


class DivisionEventsListView(LoginRequiredMixin, ListView):
    model = TeamEvent
    template_name = 'competition/division_events.html'
    context_object_name = 'events'

    def get_queryset(self):
        division_id = self.kwargs.get('division_id')
        division = get_object_or_404(Division, id=division_id)
        queryset = TeamEvent.objects.filter(division=division).order_by('date_time')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        division_id = self.kwargs.get('division_id')
        division = get_object_or_404(Division, id=division_id)
        context['division'] = division
        context['allowed_event_types'] = get_allowed_event_types(self.request.user, 'DIVISION', division=division)
        context['event_types'] = [c for c in TeamEvent.EVENT_TYPE_CHOICES if 'DIVISION' in c[0]]
        return context


class CreateDivisionEventView(LoginRequiredMixin, CreateView):
    model = TeamEvent
    form_class = DivisionEventForm
    template_name = 'competition/create_event.html'

    def get_initial(self):
        initial = super().get_initial()
        division_id = self.kwargs.get('division_id')
        initial['division'] = get_object_or_404(Division, id=division_id)
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        division_id = self.kwargs.get('division_id')
        division = get_object_or_404(Division, id=division_id)
        allowed_types = get_allowed_event_types(self.request.user, 'DIVISION', division=division)
        kwargs['division'] = division
        kwargs['allowed_event_types'] = allowed_types
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        division_id = self.kwargs.get('division_id')
        context['division'] = get_object_or_404(Division, id=division_id)
        return context

    def form_valid(self, form):
        division_id = self.kwargs.get('division_id')
        division = get_object_or_404(Division, id=division_id)
        event_type = form.cleaned_data.get('event_type')

        if not can_create_event(self.request.user, 'DIVISION', event_type, division=division):
            messages.error(self.request, "You don't have permission to create this division event.")
            return redirect('division_events', division_id=division_id)

        form.instance.division = division
        form.instance.scope = 'DIVISION'
        form.instance.created_by = self.request.user

        response = super().form_valid(form)
        try:
            self.object.propagate_to_teams()
        except Exception:
            pass

        # Warn if event counts against limits and teams are near capacity
        if form.instance.counts_against_limit:
            teams_in_division = Team.objects.filter(division=division)
            over_limit = []
            from .scheduling import team_event_count, get_week_range
            ws, we = get_week_range()
            for t in teams_in_division:
                current = team_event_count(t, ws, we)
                max_allowed = t.division.season.organization.max_events_per_team_per_week
                if current >= max_allowed:
                    over_limit.append(t.name)
            if over_limit:
                messages.warning(
                    self.request,
                    "Some teams are at their weekly event limit: " + ", ".join(over_limit)
                )

        messages.success(self.request, f"Event '{form.cleaned_data.get('title')}' created successfully.")
        return response

    def get_success_url(self):
        division_id = self.kwargs.get('division_id')
        return f'/competitions/division/{division_id}/events/'


class OrganizationEventsListView(LoginRequiredMixin, ListView):
    model = TeamEvent
    template_name = 'competition/organization_events.html'
    context_object_name = 'events'

    def get_queryset(self):
        org_id = self.kwargs.get('org_id')
        org = get_object_or_404(Organization, id=org_id)
        queryset = TeamEvent.objects.filter(organization=org).order_by('date_time')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_id = self.kwargs.get('org_id')
        org = get_object_or_404(Organization, id=org_id)
        context['organization'] = org
        context['allowed_event_types'] = get_allowed_event_types(self.request.user, 'ORGANIZATION', organization=org)
        context['event_types'] = [c for c in TeamEvent.EVENT_TYPE_CHOICES if 'LEAGUE' in c[0]]
        return context


class CreateOrganizationEventView(LoginRequiredMixin, CreateView):
    model = TeamEvent
    form_class = OrganizationEventForm
    template_name = 'competition/create_event.html'

    def get_initial(self):
        initial = super().get_initial()
        org_id = self.kwargs.get('org_id')
        initial['organization'] = get_object_or_404(Organization, id=org_id)
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        org_id = self.kwargs.get('org_id')
        org = get_object_or_404(Organization, id=org_id)
        allowed_types = get_allowed_event_types(self.request.user, 'ORGANIZATION', organization=org)
        kwargs['organization'] = org
        kwargs['allowed_event_types'] = allowed_types
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_id = self.kwargs.get('org_id')
        context['organization'] = get_object_or_404(Organization, id=org_id)
        return context

    def form_valid(self, form):
        org_id = self.kwargs.get('org_id')
        org = get_object_or_404(Organization, id=org_id)
        event_type = form.cleaned_data.get('event_type')

        if not can_create_event(self.request.user, 'ORGANIZATION', event_type, organization=org):
            messages.error(self.request, "You don't have permission to create this organization event.")
            return redirect('organization_events', org_id=org_id)

        form.instance.organization = org
        form.instance.scope = 'ORGANIZATION'
        form.instance.created_by = self.request.user

        response = super().form_valid(form)
        try:
            self.object.propagate_to_teams()
        except Exception:
            pass

        # Warn if event counts against limits and teams are near capacity
        if form.instance.counts_against_limit:
            teams_in_org = Team.objects.filter(division__season__organization=org)
            over_limit = []
            from .scheduling import team_event_count, get_week_range
            ws, we = get_week_range()
            for t in teams_in_org:
                current = team_event_count(t, ws, we)
                max_allowed = t.division.season.organization.max_events_per_team_per_week
                if current >= max_allowed:
                    over_limit.append(t.name)
            if over_limit:
                messages.warning(
                    self.request,
                    "Some teams are at their weekly event limit: " + ", ".join(over_limit)
                )

        messages.success(self.request, f"Event '{form.cleaned_data.get('title')}' created successfully.")
        return response

    def get_success_url(self):
        org_id = self.kwargs.get('org_id')
        return f'/competitions/org/{org_id}/events/'


class ScheduleEventChoiceView(LoginRequiredMixin, TemplateView):
    template_name = 'competition/schedule_event.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.request.user.profile
        organization = profile.organization
        context['organization'] = organization

        season_id = self.request.GET.get('season_id')
        season = None
        if season_id and organization:
            season = get_object_or_404(Season, id=season_id, organization=organization)
        elif organization:
            season = organization.seasons.filter(is_active=True).first() or organization.seasons.order_by('-year', '-season').first()

        context['season'] = season
        context['divisions'] = Division.objects.filter(season=season).order_by('name') if season else Division.objects.none()
        all_teams = Team.objects.filter(division__season=season).order_by('name') if season else Team.objects.none()
        user_team_ids = TeamMembership.objects.filter(
            user=self.request.user, role='COACH', is_active=True
        ).values_list('team_id', flat=True)
        user_division_ids = Team.objects.filter(id__in=user_team_ids).values_list('division_id', flat=True)

        if profile.role in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
            context['coaching_teams'] = all_teams
            context['viewable_teams'] = Team.objects.none()
        else:
            context['coaching_teams'] = all_teams.filter(id__in=user_team_ids)
            context['viewable_teams'] = all_teams.filter(division_id__in=user_division_ids).exclude(id__in=user_team_ids)
        return context


# ==============================================================================
# ADMIN SCHEDULE VIEW
# ==============================================================================

class AdminScheduleView(LoginRequiredMixin, FormView):
    """Admin schedule view for a division — shows team counts + game scheduling form."""
    template_name = 'competition/admin/schedule.html'
    form_class = ScheduleGameForm

    def get_division(self):
        return get_object_or_404(Division, id=self.kwargs['division_id'])

    def get_week_params(self):
        year = self.request.GET.get('year')
        month = self.request.GET.get('month')
        day = self.request.GET.get('day')
        if year and month and day:
            from datetime import datetime
            ref_date = datetime(int(year), int(month), int(day))
        else:
            ref_date = None
        return get_week_range(ref_date)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        division = self.get_division()
        week_start, week_end = self.get_week_params()
        max_allowed = division.season.organization.max_events_per_team_per_week
        teams = Team.objects.filter(division=division).order_by('name')

        team_data = []
        for team in teams:
            current = team_event_count(team, week_start, week_end)
            remaining = max_allowed - current
            if max_allowed > 0:
                pct = int(current / max_allowed * 100)
            else:
                pct = 0
            if pct >= 100:
                status_class = 'text-rose-400'
            elif pct >= 80:
                status_class = 'text-amber-400'
            else:
                status_class = 'text-emerald-400'
            team_data.append({
                'team': team,
                'current_count': current,
                'max_allowed': max_allowed,
                'remaining': remaining,
                'status_class': status_class,
            })

        week_events = TeamEvent.objects.filter(
            Q(division=division),
            date_time__gte=week_start,
            date_time__lte=week_end,
        ).order_by('date_time').select_related('team', 'opponent_team')

        context.update({
            'division': division,
            'season': division.season,
            'organization': division.season.organization,
            'week_start': week_start,
            'week_end': week_end,
            'team_data': team_data,
            'week_events': week_events,
            'prev_week': week_start - timedelta(days=1),
            'next_week': week_end + timedelta(days=1),
        })
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['division'] = self.get_division()
        return kwargs

    def form_valid(self, form):
        division = self.get_division()
        week_start, week_end = self.get_week_params()
        home_team = form.cleaned_data['home_team']
        away_team = form.cleaned_data['away_team']
        event_type = form.cleaned_data['event_type']
        date_time = form.cleaned_data['date_time']
        location = form.cleaned_data.get('location', '')
        counts_against_limit = form.cleaned_data.get('counts_against_limit', True)

        # Check limit for both teams
        home_allowed, home_count, home_max = team_can_add_events(home_team, 1, week_start, week_end)
        away_allowed, away_count, away_max = team_can_add_events(away_team, 1, week_start, week_end)

        if not home_allowed:
            messages.error(
                self.request,
                f"{home_team.name} has {home_count}/{home_max} events this week — cannot add more."
            )
            return self.form_invalid(form)

        if not away_allowed:
            messages.error(
                self.request,
                f"{away_team.name} has {away_count}/{away_max} events this week — cannot add more."
            )
            return self.form_invalid(form)

        # Check location conflicts
        if location:
            conflicts = get_location_conflicts(location, date_time, division)
            if conflicts:
                conflict_details = "; ".join(
                    f"{e.team.name} at {e.date_time.strftime('%I:%M %p')}" for e in conflicts
                )
                messages.error(
                    self.request,
                    f"Location conflict: \"{location}\" already has events scheduled on this date: {conflict_details}"
                )
                return self.form_invalid(form)

        # Determine title based on event type
        type_labels = dict(TeamEvent.EVENT_TYPE_CHOICES)
        type_label = type_labels.get(event_type, event_type)

        # Create a Game model for scoring-capable event types
        game_types = ['TEAM_GAME', 'TEAM_SCRIMMAGE', 'LEAGUE_TOURNAMENT', 'LEAGUE_PLAYOFF']
        game = None
        if event_type in game_types:
            game = Game.objects.create(
                season=division.season,
                home_team=home_team,
                away_team=away_team,
                date_time=date_time,
                location=location,
            )

        # Create event for home team
        home_event = TeamEvent.objects.create(
            scope='TEAM',
            organization=division.season.organization,
            division=division,
            team=home_team,
            opponent_team=away_team,
            event_type=event_type,
            title=f"{home_team.name} vs {away_team.name}",
            description=f"{type_label}: {home_team.name} vs {away_team.name}",
            date_time=date_time,
            location=location,
            counts_against_limit=counts_against_limit,
            created_by=self.request.user,
            status='SCHEDULED',
            is_home_game=True,
            game=game,
        )

        # Create event for away team
        TeamEvent.objects.create(
            scope='TEAM',
            organization=division.season.organization,
            division=division,
            team=away_team,
            opponent_team=home_team,
            event_type=event_type,
            title=f"{away_team.name} vs {home_team.name}",
            description=f"{type_label}: {away_team.name} @ {home_team.name}",
            date_time=date_time,
            location=location,
            counts_against_limit=counts_against_limit,
            created_by=self.request.user,
            status='SCHEDULED',
            is_home_game=False,
            game=game,
        )

        messages.success(self.request, f"{type_label} scheduled: {home_team.name} vs {away_team.name}")
        return redirect('admin_schedule', division_id=division.id)

    def form_invalid(self, form):
        # Re-render with form errors
        return self.render_to_response(self.get_context_data(form=form))

class GameDetailView(LoginRequiredMixin, View):
    """Show game details with lineups for both teams and optional score entry."""

    def get(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        profile = request.user.profile
        can_score_game = self._can_score_game(request, game)
        can_edit_lineup = self._can_edit_lineup(request, game)
        now = timezone.now()
        game_window_open = now >= (game.date_time - timedelta(minutes=15)) if game.date_time else False

        # Determine which team lineups to show
        is_admin_or_scorer = profile.role in ['ORG_OWNER', 'ORG_ADMIN', 'SCORER']
        can_edit_any = profile.role in ['ORG_OWNER', 'ORG_ADMIN']
        if is_admin_or_scorer:
            show_home_lineup = show_away_lineup = True
        else:
            coach_team_ids = set(Team.objects.filter(coaches=request.user).values_list('id', flat=True))
            member_team_ids = set(TeamMembership.objects.filter(
                user=request.user, role='COACH', is_active=True
            ).values_list('team_id', flat=True))
            user_team_ids = coach_team_ids | member_team_ids
            show_home_lineup = game.home_team_id in user_team_ids
            show_away_lineup = game.away_team_id in user_team_ids if game.away_team else False

        # Edit permissions per team (admins can edit both, coaches only their own, scorers none)
        if can_edit_any:
            can_edit_home = can_edit_away = True
        elif profile.role == 'SCORER':
            can_edit_home = can_edit_away = False
        else:
            coach_team_ids = set(Team.objects.filter(coaches=request.user).values_list('id', flat=True))
            member_team_ids = set(TeamMembership.objects.filter(
                user=request.user, role='COACH', is_active=True
            ).values_list('team_id', flat=True))
            user_team_ids = coach_team_ids | member_team_ids
            can_edit_home = game.home_team_id in user_team_ids
            can_edit_away = game.away_team_id in user_team_ids if game.away_team else False

        # During the game window, everyone can see the box score
        if game_window_open:
            show_home_lineup = show_away_lineup = True

        def split_entries(team):
            all_entries = GameLineupEntry.objects.filter(game=game, team=team).select_related('player').order_by('batting_order')
            field = [e for e in all_entries if e.position]
            bench = [e for e in all_entries if not e.position]
            return field, bench

        home_field, home_bench = split_entries(game.home_team) if show_home_lineup else ([], [])
        away_field, away_bench = split_entries(game.away_team) if show_away_lineup and game.away_team else ([], [])

        home_form = LineupEntryForm(team=game.home_team, game=game) if can_edit_home else None
        away_form = LineupEntryForm(team=game.away_team, game=game) if can_edit_away and game.away_team else None

        conflict = request.session.get('pending_conflict')

        return render(request, 'competition/game_detail.html', {
            'game': game,
            'home_field': home_field,
            'home_bench': home_bench,
            'away_field': away_field,
            'away_bench': away_bench,
            'home_form': home_form,
            'away_form': away_form,
            'can_score_game': can_score_game,
            'can_edit_lineup': can_edit_lineup,
            'can_edit_home': can_edit_home,
            'can_edit_away': can_edit_away,
            'show_home_lineup': show_home_lineup,
            'show_away_lineup': show_away_lineup,
            'score_form': GameScoreForm() if can_score_game and not game.is_completed else None,
            'position_choices': DEFENSIVE_POSITION_CHOICES,
            'conflict': conflict,
            'game_window_open': game_window_open,
            'runners': game.scoring_data.get('runners', {'first': None, 'second': None, 'third': None}),
            'current_pitcher': game.scoring_data.get('current_pitcher', {}),
            'pitches': game.scoring_data.get('pitches', []),
        })

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        action = request.POST.get('action')

        # --- Actions that need score_game permission ---
        scoring_actions = ['save_score', 'start_game', 'record_pitch', 'record_nonpitch', 'set_pitcher', 'reset_game']
        if action in scoring_actions:
            if not self._can_score_game(request, game):
                messages.error(request, "You don't have scoring permission.")
                return redirect('game_detail', game_id=game.id)

        # --- Actions that need edit_lineup permission ---
        lineup_actions = ['add_entry', 'delete_entry', 'update_entry', 'resolve_conflict', 'cancel_conflict']
        if action in lineup_actions:
            if not self._can_edit_lineup(request, game):
                messages.error(request, "You don't have permission to modify the lineup.")
                return redirect('game_detail', game_id=game.id)

        # --- Emergency sub (scorers can do this) ---
        if action == 'emergency_sub':
            if not self._can_score_game(request, game):
                messages.error(request, "You don't have permission.")
                return redirect('game_detail', game_id=game.id)
            entry_id = request.POST.get('entry_id')
            entry = get_object_or_404(GameLineupEntry, id=entry_id, game=game)
            entry.is_active = not entry.is_active
            entry.save()
            status = "activated" if entry.is_active else "subbed out"
            messages.success(request, f"{entry.player} {status}.")
            return redirect('game_detail', game_id=game.id)

        # --- Skip batter ---
        if action == 'skip_batter':
            if not self._can_score_game(request, game):
                messages.error(request, "You don't have permission.")
                return redirect('game_detail', game_id=game.id)
            side = 'home' if game.is_top_inning else 'away'
            from .api import _advance_batter
            _advance_batter(game, side)
            game.save()
            messages.success(request, "Batter skipped.")
            return redirect('game_detail', game_id=game.id)

        # Score entry
        if action == 'save_score':
            form = GameScoreForm(request.POST)
            if form.is_valid():
                game.home_score = form.cleaned_data['home_score']
                game.away_score = form.cleaned_data['away_score']
                game.is_completed = True
                game.is_live = False
                game.save()
                messages.success(request, "Score recorded.")
            else:
                messages.error(request, "Invalid score values.")
            return redirect('game_detail', game_id=game.id)

        # Start game
        if action == 'start_game':
            game.is_live = True
            from .api import _init_scoring_data, _get_current_batter_player_id, _get_player_name
            _init_scoring_data(game)
            pid = _get_current_batter_player_id(game, 'away')
            if pid:
                game.scoring_data['current_batter'] = {
                    'side': 'away',
                    'player_id': pid,
                    'player_name': _get_player_name(pid),
                }
            game.save(update_fields=['is_live', 'scoring_data'])
            messages.success(request, "Game started!")
            return redirect('game_score', game_id=game.id)

        # Reset game — clear all scoring data, return to pre-game state
        if action == 'reset_game':
            game.is_live = False
            game.is_completed = False
            game.current_inning = 1
            game.is_top_inning = True
            game.outs = 0
            game.balls = 0
            game.strikes = 0
            game.pitch_count = 0
            game.home_score = 0
            game.away_score = 0
            game.scoring_data = {}
            game.save()
            messages.success(request, "Game has been reset.")
            return redirect('game_detail', game_id=game.id)

        # Record pitch
        if action == 'record_pitch':
            pitch_type = request.POST.get('pitch_type')
            valid_types = {
                'ball', 'strike', 'foul', 'hit', 'out',
                'ball_outside', 'ball_inside', 'ball_high', 'ball_low', 'ball_dirt',
                'strike_called', 'strike_swinging', 'strike_foul_tip',
                'single', 'double', 'triple', 'homerun',
                'out_ground', 'out_fly', 'out_line', 'out_pop', 'strikeout',
                'double_play', 'triple_play', 'pickoff',
                'steal', 'caught_stealing', 'hit_by_pitch',
                'sac_bunt', 'sac_fly', 'error', 'fielders_choice',
                'wild_pitch', 'passed_ball', 'balk', 'dropped_third_strike',
                'infield_fly', 'bunt', 'bunt_foul',
            }
            if pitch_type not in valid_types:
                messages.error(request, "Invalid pitch type.")
                return redirect('game_detail', game_id=game.id)
            extra = _build_extra_from_post(request.POST, pitch_type)
            from .api import _apply_record_pitch
            _apply_record_pitch(game, pitch_type, extra=extra)
            game.save()
            return redirect('game_detail', game_id=game.id)

        # Record non-pitch event (same handler, but via nonpitch action)
        if action == 'record_nonpitch':
            pitch_type = request.POST.get('pitch_type')
            valid_nonpitch = {
                'steal', 'caught_stealing', 'wild_pitch', 'passed_ball', 'balk',
                'pickoff',
            }
            if pitch_type not in valid_nonpitch:
                messages.error(request, "Invalid non-pitch event type.")
                return redirect('game_detail', game_id=game.id)
            extra = _build_extra_from_post(request.POST, pitch_type)
            from .api import _apply_record_pitch
            _apply_record_pitch(game, pitch_type, extra=extra)
            game.save()
            return redirect('game_detail', game_id=game.id)

        # Set pitcher
            player_id = request.POST.get('pitcher_player_id')
            side = request.POST.get('side')
            if player_id and side in ('home', 'away'):
                from profiles.models import Player
                player = get_object_or_404(Player, id=player_id)
                game.scoring_data.setdefault('current_pitcher', {})[side] = {
                    'player_id': player.id,
                    'player_name': str(player),
                }
                game.save()
                messages.success(request, f"{player} set as pitcher for {side}.")
            return redirect('game_detail', game_id=game.id)

        # Add lineup entry
        if action == 'add_entry':
            team_id = request.POST.get('team_id')
            team = get_object_or_404(Team, id=team_id)
            form = LineupEntryForm(request.POST, team=team, game=game)
            if form.is_valid():
                player = form.cleaned_data['player']
                batting_order = form.cleaned_data['batting_order']
                position = form.cleaned_data.get('position', '')

                if position:
                    conflict = GameLineupEntry.objects.filter(
                        game=game, team=team, position=position
                    ).exclude(player=player).first()
                    if conflict:
                        request.session['pending_conflict'] = {
                            'action': 'add_entry',
                            'team_id': str(team.id),
                            'player_id': player.id,
                            'player_name': str(player),
                            'batting_order': batting_order,
                            'position': position,
                            'conflict_entry_id': conflict.id,
                            'conflict_player_name': str(conflict.player),
                        }
                        from django.urls import reverse
                        return redirect(f"{reverse('game_detail', kwargs={'game_id': game.id})}?conflict=1")

                entry, created = GameLineupEntry.objects.get_or_create(
                    game=game, player=player,
                    defaults={'team': team, 'batting_order': batting_order, 'position': position}
                )
                if not created:
                    entry.team = team
                    entry.batting_order = batting_order
                    entry.position = position
                    entry.save()
                messages.success(request, f"Added {player} to lineup.")
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, error)
            return redirect('game_detail', game_id=game.id)

        # Delete lineup entry
        if action == 'delete_entry':
            entry_id = request.POST.get('entry_id')
            entry = get_object_or_404(GameLineupEntry, id=entry_id, game=game)
            entry.delete()
            messages.success(request, "Entry removed from lineup.")
            return redirect('game_detail', game_id=game.id)

        # Update entry position/batting order
        if action == 'update_entry':
            entry_id = request.POST.get('entry_id')
            entry = get_object_or_404(GameLineupEntry, id=entry_id, game=game)
            batting_order = request.POST.get('batting_order')
            position = request.POST.get('position', '')

            if batting_order:
                try:
                    bo = int(batting_order)
                except (ValueError, TypeError):
                    messages.error(request, "Invalid batting order number.")
                    return redirect('game_detail', game_id=game.id)
                entry.batting_order = bo

            if position:
                conflict = GameLineupEntry.objects.filter(
                    game=game, team=entry.team, position=position
                ).exclude(id=entry.id).first()
                if conflict:
                    request.session['pending_conflict'] = {
                        'action': 'update_entry',
                        'entry_id': entry.id,
                        'team_id': str(entry.team.id),
                        'player_name': str(entry.player),
                        'batting_order': entry.batting_order,
                        'position': position,
                        'conflict_entry_id': conflict.id,
                        'conflict_player_name': str(conflict.player),
                    }
                    from django.urls import reverse
                    return redirect(f"{reverse('game_detail', kwargs={'game_id': game.id})}?conflict=1")
                entry.position = position

            entry.save()
            messages.success(request, "Lineup entry updated.")
            return redirect('game_detail', game_id=game.id)

        # Resolve position conflict — overwrite
        if action == 'resolve_conflict':
            pending = request.session.pop('pending_conflict', None)
            if not pending:
                return redirect('game_detail', game_id=game.id)

            conflict_entry = get_object_or_404(GameLineupEntry, id=pending['conflict_entry_id'])
            conflict_entry.position = ''
            conflict_entry.save()

            if pending['action'] == 'add_entry':
                team = get_object_or_404(Team, id=pending['team_id'])
                player = get_object_or_404(Player, id=pending['player_id'])
                entry, created = GameLineupEntry.objects.get_or_create(
                    game=game, player=player,
                    defaults={'team': team, 'batting_order': pending['batting_order'], 'position': pending['position']}
                )
                if not created:
                    entry.team = team
                    entry.batting_order = pending['batting_order']
                    entry.position = pending['position']
                    entry.save()
            elif pending['action'] == 'update_entry':
                entry = get_object_or_404(GameLineupEntry, id=pending['entry_id'])
                entry.position = pending['position']
                if pending.get('batting_order'):
                    entry.batting_order = pending['batting_order']
                entry.save()

            messages.success(request, f"Assigned {pending['player_name']} to {pending['position']}. {pending['conflict_player_name']} moved to bench.")
            return redirect('game_detail', game_id=game.id)

        # Cancel position conflict
        if action == 'cancel_conflict':
            request.session.pop('pending_conflict', None)
            return redirect('game_detail', game_id=game.id)

        return redirect('game_detail', game_id=game.id)

    def _can_edit_lineup(self, request, game):
        """Admins and coaches of either team can edit lineups. Scorers cannot."""
        profile = request.user.profile
        if profile.role in ['ORG_OWNER', 'ORG_ADMIN']:
            return True
        team_ids = set(Team.objects.filter(coaches=request.user).values_list('id', flat=True))
        membership_ids = set(TeamMembership.objects.filter(
            user=request.user, role='COACH', is_active=True
        ).values_list('team_id', flat=True))
        all_ids = team_ids | membership_ids
        return game.home_team_id in all_ids or game.away_team_id in all_ids

    def _can_score_game(self, request, game):
        """Scorers, admins, and coaches of either team can score."""
        profile = request.user.profile
        if profile.role in ['ORG_OWNER', 'ORG_ADMIN', 'SCORER']:
            return True
        team_ids = set(Team.objects.filter(coaches=request.user).values_list('id', flat=True))
        membership_ids = set(TeamMembership.objects.filter(
            user=request.user, role='COACH', is_active=True
        ).values_list('team_id', flat=True))
        all_ids = team_ids | membership_ids
        return game.home_team_id in all_ids or game.away_team_id in all_ids


class GameScoreView(LoginRequiredMixin, View):
    """Dedicated live scoring interface for a game."""

    def get(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.is_live and not game.is_completed:
            messages.info(request, "Game hasn't started yet.")
            return redirect('game_detail', game_id=game.id)
        if not self._can_score_game(request, game):
            messages.error(request, "You don't have scoring permission.")
            return redirect('game_detail', game_id=game.id)

        profile = request.user.profile
        now = timezone.now()
        game_window_open = now >= (game.date_time - timedelta(minutes=15)) if game.date_time else False

        def split_entries(team):
            all_entries = GameLineupEntry.objects.filter(game=game, team=team).select_related('player').order_by('batting_order')
            field = [e for e in all_entries if e.position]
            bench = [e for e in all_entries if not e.position]
            return field, bench

        home_field, home_bench = split_entries(game.home_team)
        away_field, away_bench = split_entries(game.away_team) if game.away_team else ([], [])

        pitches = game.scoring_data.get('pitches', [])
        current_pitcher = game.scoring_data.get('current_pitcher', {})
        current_batter = game.scoring_data.get('current_batter', {})
        runners = game.scoring_data.get('runners', {'first': None, 'second': None, 'third': None})

        # Compute stats
        from .api import compute_game_stats
        stats = compute_game_stats(game)

        # Split batters by team
        home_lineup = GameLineupEntry.objects.filter(game=game, team=game.home_team).select_related('player')
        home_player_ids = set(e.player_id for e in home_lineup)
        home_batters = {pid: s for pid, s in stats['batters'].items() if pid in home_player_ids}
        away_batters = {pid: s for pid, s in stats['batters'].items() if pid not in home_player_ids}
        home_pitchers = {pid: s for pid, s in stats['pitchers'].items() if pid in home_player_ids}
        away_pitchers = {pid: s for pid, s in stats['pitchers'].items() if pid not in home_player_ids}

        pitching_side = 'home' if game.is_top_inning else 'away'
        pitching_field = home_field if pitching_side == 'home' else away_field

        return render(request, 'competition/game_score.html', {
            'game': game,
            'home_field': home_field,
            'away_field': away_field,
            'pitching_side': pitching_side,
            'pitching_field': pitching_field,
            'pitches': pitches,
            'current_pitcher': current_pitcher,
            'current_batter': current_batter,
            'position_choices': DEFENSIVE_POSITION_CHOICES,
            'runners': runners,
            'game_window_open': game_window_open,
            'home_batters': home_batters,
            'away_batters': away_batters,
            'home_pitchers': home_pitchers,
            'away_pitchers': away_pitchers,
            'innings_data': stats['innings'],
        })

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not self._can_score_game(request, game):
            messages.error(request, "You don't have scoring permission.")
            return redirect('game_score', game_id=game.id)

        action = request.POST.get('action')

        if action == 'record_pitch':
            pitch_type = request.POST.get('pitch_type')
            valid_types = {
                'ball', 'strike', 'foul', 'hit', 'out',
                'ball_outside', 'ball_inside', 'ball_high', 'ball_low', 'ball_dirt',
                'strike_called', 'strike_swinging', 'strike_foul_tip',
                'single', 'double', 'triple', 'homerun',
                'out_ground', 'out_fly', 'out_line', 'out_pop', 'strikeout',
                'double_play', 'triple_play', 'pickoff',
                'steal', 'caught_stealing', 'hit_by_pitch',
                'sac_bunt', 'sac_fly', 'error', 'fielders_choice',
                'wild_pitch', 'passed_ball', 'balk', 'dropped_third_strike',
                'infield_fly', 'bunt', 'bunt_foul',
            }
            if pitch_type not in valid_types:
                messages.error(request, "Invalid pitch type.")
                return redirect('game_score', game_id=game.id)
            extra = _build_extra_from_post(request.POST, pitch_type)
            from .api import _apply_record_pitch
            _apply_record_pitch(game, pitch_type, extra=extra)
            game.save()
            return redirect('game_score', game_id=game.id)

        if action == 'set_pitcher':
            player_id = request.POST.get('pitcher_player_id')
            side = request.POST.get('side')
            if player_id and side in ('home', 'away'):
                from profiles.models import Player
                player = get_object_or_404(Player, id=player_id)
                game.scoring_data.setdefault('current_pitcher', {})[side] = {
                    'player_id': player.id,
                    'player_name': str(player),
                }
                game.save()
                messages.success(request, f"{player} set as pitcher for {side}.")
            return redirect('game_score', game_id=game.id)

        if action == 'emergency_sub':
            entry_id = request.POST.get('entry_id')
            entry = get_object_or_404(GameLineupEntry, id=entry_id, game=game)
            entry.is_active = not entry.is_active
            entry.save()
            status = "activated" if entry.is_active else "subbed out"
            messages.success(request, f"{entry.player} {status}.")
            return redirect('game_score', game_id=game.id)

        if action == 'skip_batter':
            side = 'home' if game.is_top_inning else 'away'
            from .api import _advance_batter
            _advance_batter(game, side)
            game.save()
            messages.success(request, "Batter skipped.")
            return redirect('game_score', game_id=game.id)

        if action == 'save_score':
            form = GameScoreForm(request.POST)
            if form.is_valid():
                game.home_score = form.cleaned_data['home_score']
                game.away_score = form.cleaned_data['away_score']
                game.is_completed = True
                game.is_live = False
                game.save()
                messages.success(request, "Score recorded.")
            else:
                messages.error(request, "Invalid score values.")
            return redirect('game_detail', game_id=game.id)

        return redirect('game_score', game_id=game.id)

    def _can_score_game(self, request, game):
        profile = request.user.profile
        if profile.role in ['ORG_OWNER', 'ORG_ADMIN', 'SCORER']:
            return True
        team_ids = set(Team.objects.filter(coaches=request.user).values_list('id', flat=True))
        membership_ids = set(TeamMembership.objects.filter(
            user=request.user, role='COACH', is_active=True
        ).values_list('team_id', flat=True))
        all_ids = team_ids | membership_ids
        return game.home_team_id in all_ids or game.away_team_id in all_ids

