from django.contrib import admin
from django.urls import path, include
from config.api import api
from django.views.generic import RedirectView
from competition.views import game_stream

urlpatterns = [
    path('admin/', admin.site.urls),
    # SSE must precede the ninja include so it is matched first.
    path('api/competition/games/<uuid:game_id>/stream', game_stream, name='game_stream'),
    path("api/", api.urls), # This wires up all your endpoints
    path('', RedirectView.as_view(pattern_name='landing_portal', permanent=False)),
    path('profiles/', include('profiles.urls')), # Include the profiles app URLs
    path('competitions/', include('competition.urls')),  # Include competition event URLs
]