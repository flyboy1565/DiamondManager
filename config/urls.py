from django.contrib import admin
from django.urls import path, include
from config.api import api

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", api.urls), # This wires up all your endpoints
    path('profiles/', include('profiles.urls')), # Include the profiles app URLs
]