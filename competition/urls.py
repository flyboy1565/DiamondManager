from django.urls import path
from . import views

urlpatterns = [
    # Game detail with lineup
    path('game/<uuid:game_id>/', views.GameDetailView.as_view(), name='game_detail'),
    # Live scoring interface
    path('game/<uuid:game_id>/score/', views.GameScoreView.as_view(), name='game_score'),
    # Event listing and creation
    path('team/<uuid:team_id>/events/', views.TeamEventsListView.as_view(), name='team_events'),
    path('team/<uuid:team_id>/events/new/', views.CreateTeamEventView.as_view(), name='create_event'),
    path('team/<uuid:team_id>/events/<slug:unused>/', views.TeamEventsListView.as_view(), name='team_events_slug'),
    
    # Event detail, editing, and score recording
    path('event/<uuid:event_id>/', views.EventDetailView.as_view(), name='event_detail'),
    path('event/<uuid:event_id>/edit/', views.EditTeamEventView.as_view(), name='edit_event'),
    # Schedule event helper
    path('schedule/', views.ScheduleEventChoiceView.as_view(), name='schedule_event'),
    # Division-level events
    path('division/<int:division_id>/events/', views.DivisionEventsListView.as_view(), name='division_events'),
    path('division/<int:division_id>/events/new/', views.CreateDivisionEventView.as_view(), name='create_division_event'),

    # Organization/league-level events
    path('org/<uuid:org_id>/events/', views.OrganizationEventsListView.as_view(), name='organization_events'),
    path('org/<uuid:org_id>/events/new/', views.CreateOrganizationEventView.as_view(), name='create_organization_event'),

    # Admin schedule view
    path('admin/schedule/<int:division_id>/', views.AdminScheduleView.as_view(), name='admin_schedule'),
]
