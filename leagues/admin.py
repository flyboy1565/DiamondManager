from django.contrib import admin
from .models import Organization, Season, Team, Division, Facility

models_to_register = [Season, Team, Division]

for model in models_to_register:
    admin_class = type(
        f"{model.__name__}Admin", 
        (admin.ModelAdmin,), 
        {
            "list_display": [field.name for field in model._meta.fields]
        }
    )
    admin.site.register(model, admin_class)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Organization._meta.fields]
    fieldsets = (
        (None, {
            'fields': ('name', 'city', 'state', 'zip_code')
        }),
        ('Scheduling Limits', {
            'fields': ('max_events_per_team_per_week',),
            'description': 'Maximum number of countable events per team per week (Mon-Sun)'
        }),
        ('Facilities', {
            'fields': (),
            'description': 'Manage facilities via the organization settings page. Facilities are used as location dropdown options when scheduling events.'
        }),
    )


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ['name', 'field_name', 'address', 'organization']
    list_filter = ['organization']
    search_fields = ['name', 'address', 'field_name']