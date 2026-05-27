from django.urls import path
from .views import (
    CreateOrganizationView, 
    CreateSeasonView, 
    CreateDivisionView,
    CreateTeamView,
    RosterOnboardingView,
    LandingPortalView, 
    PortalLoginView, 
    PortalRegisterOrgView, 
    PortalVerifyTokenView,
    DashboardView,
    SeasonDetailView,
    DivisionEditView,
    TeamDetailView,
    CreateCoachView,
    CreatePlayerView,
    CreateGameView,
)

urlpatterns = [
    path('', LandingPortalView.as_view(), name='landing_portal'),
    path('portal/login/', PortalLoginView.as_view(), name='portal_login'),
    path('portal/register-org/', PortalRegisterOrgView.as_view(), name='portal_register_org'),
    path('portal/verify-token/', PortalVerifyTokenView.as_view(), name='portal_verify_token'),
    
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('admin/org/new/', CreateOrganizationView.as_view(), name='create_org'),
    path('admin/season/new/', CreateSeasonView.as_view(), name='create_season'),
    path('admin/season/<uuid:season_id>/divisions/new/', CreateDivisionView.as_view(), name='create_division'),
    path('admin/season/<uuid:season_id>/', SeasonDetailView.as_view(), name='season_detail'),
    path('admin/season/<uuid:season_id>/onboard/', RosterOnboardingView.as_view(), name='roster_onboarding'),
    path('admin/division/<int:division_id>/edit/', DivisionEditView.as_view(), name='edit_division'),
    path('admin/team/<int:division_id>/team/', CreateTeamView.as_view(), name='create_team'),
    path('admin/team/<uuid:team_id>/edit/', TeamDetailView.as_view(), name='team_detail'),
    path('admin/team/<uuid:team_id>/coaches/new/', CreateCoachView.as_view(), name='create_coach'),
    path('admin/team/<uuid:team_id>/players/new/', CreatePlayerView.as_view(), name='create_player'),
    path('admin/team/<uuid:team_id>/games/new/', CreateGameView.as_view(), name='create_game'),
]