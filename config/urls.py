from django.contrib import admin
from django.urls import path, include
from config.api import api
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", api.urls), # This wires up all your endpoints
    path('', RedirectView.as_view(pattern_name='landing_portal', permanent=False)),
    path('profiles/', include('profiles.urls')), # Include the profiles app URLs
]