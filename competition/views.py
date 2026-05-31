from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db.models import Q
from leagues.models import Team
from .models import TeamEvent
from .forms import TeamEventForm, GameScoreForm
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
        context['allowed_event_types'] = get_allowed_event_types(self.request.user, team)
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
        allowed_types = get_allowed_event_types(self.request.user, team)
        kwargs['team'] = team
        kwargs['allowed_event_types'] = allowed_types
        return kwargs
    
    def form_valid(self, form):
        team_id = self.kwargs.get('team_id')
        team = get_object_or_404(Team, id=team_id)
        event_type = form.cleaned_data.get('event_type')
        
        # Check permissions
        if not can_create_event(self.request.user, team, event_type):
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
        allowed_types = get_allowed_event_types(self.request.user, event.team)
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
        
        # Show score form for game/scrimmage events
        if event.event_type in ['GAME', 'SCRIMMAGE']:
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

