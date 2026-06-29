from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView
from django.db.models import Q
from leagues.models import Team, Division, Organization, Season
from .models import TeamEvent
from .forms import TeamEventForm, GameScoreForm, DivisionEventForm, OrganizationEventForm
from .permissions import can_create_event, can_edit_event, get_allowed_event_types


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
        return context


class CreateTeamEventView(LoginRequiredMixin, CreateView):
    """
    Create a new team event with permission checks.
    """
    model = TeamEvent
    form_class = TeamEventForm
    template_name = 'competition/create_event.html'
    
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
        context['teams'] = Team.objects.filter(division__season=season).order_by('name') if season else Team.objects.none()
        return context

