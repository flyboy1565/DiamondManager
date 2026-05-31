import uuid
from django.db import models
from django.contrib.auth.models import User
from leagues.models import Team, Season


class TeamEvent(models.Model):
    """
    Unified event model for team activities: games, practices, tournaments, scrimmages, hangouts, ceremonies.
    """
    EVENT_TYPE_CHOICES = [
        ('OPENING_DAY', 'Opening Day'),
        ('CLOSING_CEREMONY', 'Closing Ceremony'),
        ('GAME', 'Game'),
        ('PRACTICE', 'Practice'),
        ('TOURNAMENT', 'Tournament'),
        ('SCRIMMAGE', 'Scrimmage'),
        ('HANGOUT', 'Hangout'),
    ]
    
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),
    ]
    
    PRACTICE_FOCUS_CHOICES = [
        ('pitching', 'Pitching'),
        ('hitting', 'Hitting'),
        ('fielding', 'Fielding'),
        ('conditioning', 'Conditioning'),
        ('base_running', 'Base Running'),
        ('general', 'General Practice'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team_events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    date_time = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)
    
    # Creator tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='team_events_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Event status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    
    # Game-specific fields
    opponent_team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='opponent_events')
    home_score = models.PositiveIntegerField(null=True, blank=True)
    away_score = models.PositiveIntegerField(null=True, blank=True)
    is_home_game = models.BooleanField(null=True, blank=True)
    
    # Game state fields (live scoring)
    is_live = models.BooleanField(default=False)
    current_inning = models.PositiveIntegerField(default=1, null=True, blank=True)
    is_top_inning = models.BooleanField(default=True, null=True, blank=True)
    outs = models.PositiveIntegerField(default=0, null=True, blank=True)
    balls = models.PositiveIntegerField(default=0, null=True, blank=True)
    strikes = models.PositiveIntegerField(default=0, null=True, blank=True)
    pitch_count = models.PositiveIntegerField(default=0, null=True, blank=True)
    
    # Practice-specific fields
    practice_focus = models.CharField(max_length=50, choices=PRACTICE_FOCUS_CHOICES, null=True, blank=True)
    attendance_required = models.BooleanField(default=False)
    
    # Tournament-specific fields
    tournament_name = models.CharField(max_length=255, null=True, blank=True)
    tournament_division = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        ordering = ['-date_time']
        indexes = [
            models.Index(fields=['team', 'date_time']),
            models.Index(fields=['event_type', 'status']),
        ]
    
    def __str__(self):
        return f"{self.team.name} - {self.get_event_type_display()} - {self.date_time.strftime('%m/%d/%Y')}"
    
    @property
    def is_completed(self):
        return self.status == 'COMPLETED'


class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='games')
    
    # We need related_name here because both point to the 'Team' model
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='competition_home_games')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='competition_away_games')
    
    date_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    
    home_score = models.PositiveIntegerField(default=0)
    away_score = models.PositiveIntegerField(default=0)
    is_live = models.BooleanField(default=False)
    current_inning = models.PositiveIntegerField(default=1)
    is_top_inning = models.BooleanField(default=True)
    outs = models.PositiveIntegerField(default=0)
    balls = models.PositiveIntegerField(default=0)
    strikes = models.PositiveIntegerField(default=0)
    pitch_count = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} - {self.date_time.strftime('%m/%d')}"

class GameLineupEntry(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='lineup_entries')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    player = models.ForeignKey('profiles.Player', on_delete=models.CASCADE)
    batting_order = models.PositiveIntegerField()
    position = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['batting_order']
        unique_together = ('game', 'player')

    def __str__(self):
        return f"{self.game} - {self.player} ({self.batting_order})"

class PlayerGameStat(models.Model):
    player = models.ForeignKey('profiles.Player', on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='player_stats')
    
    # Baseball example - customize as needed
    at_bats = models.PositiveIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0)
    runs = models.PositiveIntegerField(default=0)
    rbi = models.PositiveIntegerField(default=0)
    innings_pitched = models.DecimalField(max_digits=4, decimal_places=1, default=0.0)
    strikeouts_thrown = models.PositiveIntegerField(default=0)
    pitches_thrown = models.PositiveIntegerField(default=0)    
    
    class Meta:
        unique_together = ('player', 'game') # One stat entry per player per game