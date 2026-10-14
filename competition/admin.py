from django.contrib import admin
from .models import Game, PlayerGameStat, TeamEvent, ScoringToken


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'home_team', 'away_team', 'date_time', 'is_live', 'is_completed',
        'home_score', 'away_score', 'current_inning', 'outs', 'balls', 'strikes',
        'stream_status', 'srt_stream_id', 'youtube_channel_display', 'youtube_video_id',
        'stream_started_at', 'stream_ended_at', 'is_streaming_enabled',
    ]
    list_filter = ['stream_status', 'is_streaming_enabled', 'is_live', 'is_completed']
    readonly_fields = [
        'youtube_broadcast_id', 'youtube_stream_id', 'youtube_video_id',
        'srt_stream_id', 'stream_status', 'stream_started_at', 'stream_ended_at',
        'stream_error', 'scoring_data',
    ]
    search_fields = ['id', 'home_team__name', 'away_team__name', 'location']

    @admin.display(description='YouTube Channel')
    def youtube_channel_display(self, obj):
        cfg = getattr(obj.season.organization, 'youtube_config', None)
        if cfg and cfg.youtube_channel_id:
            return cfg.youtube_channel_id
        return '-'

    actions = ['mark_preparing', 'mark_idle']

    def mark_preparing(self, request, queryset):
        updated = queryset.update(stream_status='preparing')
        self.message_user(request, f'{updated} game(s) set to preparing.')
    mark_preparing.short_description = 'Set stream status to preparing'

    def mark_idle(self, request, queryset):
        updated = queryset.update(stream_status='idle', stream_ended_at=None, is_streaming_enabled=True)
        self.message_user(request, f'{updated} game(s) set to idle.')
    mark_idle.short_description = 'Reset stream status to idle'


@admin.register(ScoringToken)
class ScoringTokenAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'token', 'created_by', 'expires_at', 'is_active']
    list_filter = ['is_active']
    search_fields = ['token']


admin.site.register(PlayerGameStat)
admin.site.register(TeamEvent)