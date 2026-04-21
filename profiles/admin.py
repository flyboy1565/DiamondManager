from django.contrib import admin
from .models import Profile

models_to_register = [Profile,]

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