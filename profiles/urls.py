from django.urls import path
from .views import CreateOrganizationView, CreateSeasonView, RosterOnboardingView

urlpatterns = [
    path('admin/org/new/', CreateOrganizationView.as_view(), name='create_org'),
    path('admin/season/new/', CreateSeasonView.as_view(), name='create_season'),
    path('admin/season/<uuid:season_id>/onboard/', RosterOnboardingView.as_view(), name='roster_onboarding'),
]