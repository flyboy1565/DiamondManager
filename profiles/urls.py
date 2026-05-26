from django.urls import path
from .views import (
    CreateOrganizationView, 
    CreateSeasonView, 
    RosterOnboardingView,
    LandingPortalView, 
    PortalLoginView, 
    PortalRegisterOrgView, 
    PortalVerifyTokenView,
    DashboardView,
)

urlpatterns = [
    path('', LandingPortalView.as_view(), name='landing_portal'),
    path('portal/login/', PortalLoginView.as_view(), name='portal_login'),
    path('portal/register-org/', PortalRegisterOrgView.as_view(), name='portal_register_org'),
    path('portal/verify-token/', PortalVerifyTokenView.as_view(), name='portal_verify_token'),
    
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('admin/org/new/', CreateOrganizationView.as_view(), name='create_org'),
    path('admin/season/new/', CreateSeasonView.as_view(), name='create_season'),
    path('admin/season/<uuid:season_id>/onboard/', RosterOnboardingView.as_view(), name='roster_onboarding'),
]