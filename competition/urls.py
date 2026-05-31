from django.urls import path
from . import views

urlpatterns = [
    # Event listing and creation
    path('team/<uuid:team_id>/events/', views.TeamEventsListView.as_view(), name='team_events'),
    path('team/<uuid:team_id>/events/new/', views.CreateTeamEventView.as_view(), name='create_event'),
    
    # Event detail, editing, and score recording
    path('event/<uuid:event_id>/', views.EventDetailView.as_view(), name='event_detail'),
    path('event/<uuid:event_id>/edit/', views.EditTeamEventView.as_view(), name='edit_event'),
]
