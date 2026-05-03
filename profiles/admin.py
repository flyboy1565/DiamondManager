from django.contrib import admin
from .models import Profile, TeamMembership, Player, PlayerMembership

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'phone_number']
    list_filter = ['role']
    search_fields = ['user__username', 'user__email']

@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'team', 'role', 'is_active', 'joined_at']
    list_filter = ['role', 'is_active', 'team']
    search_fields = ['user__username', 'team__name']
    raw_id_fields = ['user', 'team']  # For better performance with large datasets

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'guardian', 'date_of_birth']
    search_fields = ['first_name', 'last_name', 'guardian__username']

@admin.register(PlayerMembership)
class PlayerMembershipAdmin(admin.ModelAdmin):
    list_display = ['player', 'team', 'jersey_number', 'is_active']
    list_filter = ['is_active', 'team']
    search_fields = ['player__first_name', 'player__last_name', 'team__name']
    raw_id_fields = ['player', 'team']
