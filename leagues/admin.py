from django.contrib import admin
from .models import Organization, Season, Team, Player, Game

models_to_register = [Organization, Season, Team, Player, Game]

for model in models_to_register:
    # Create a dynamic subclass of ModelAdmin for each model
    admin_class = type(
        f"{model.__name__}Admin", 
        (admin.ModelAdmin,), 
        {
            "list_display": [field.name for field in model._meta.fields]
        }
    )
    admin.site.register(model, admin_class)