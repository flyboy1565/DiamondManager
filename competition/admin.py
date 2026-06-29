from django.contrib import admin
from .models import Game, PlayerGameStat, TeamEvent, ScoringToken


class GameAdmin(admin.ModelAdmin):
    list_display = ['id', 'home_team', 'away_team', 'date_time', 'is_live', 'is_completed',
                    'home_score', 'away_score', 'current_inning', 'outs', 'balls', 'strikes']


class ScoringTokenAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'token', 'created_by', 'expires_at', 'is_active']


admin.site.register(Game, GameAdmin)
admin.site.register(PlayerGameStat)
admin.site.register(TeamEvent)
admin.site.register(ScoringToken, ScoringTokenAdmin)