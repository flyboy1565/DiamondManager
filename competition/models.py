import uuid
from django.db import models
from django.contrib.auth.models import User
from leagues.models import Team, Season, Organization, Division


class TeamEvent(models.Model):
    """
    Unified event model for team/division/organization activities.
    Supports events at multiple levels: organization, division, or team.
    """
    SCOPE_CHOICES = [
        ('ORGANIZATION', 'Organization/League'),
        ('DIVISION', 'Division'),
        ('TEAM', 'Team'),
    ]
    
    EVENT_TYPE_CHOICES = [
        # Organization/League level events
        ('LEAGUE_OPENING_DAY', 'League Opening Day'),
        ('LEAGUE_CLOSING_CEREMONY', 'League Closing Ceremony'),
        ('LEAGUE_TOURNAMENT', 'League Tournament'),
        ('LEAGUE_ALLSTAR_GAME', 'League All-Star Game'),
        ('LEAGUE_AWARDS', 'League Awards Ceremony'),
        ('LEAGUE_PLAYOFF', 'League Playoff'),
        ('LEAGUE_ANNOUNCEMENT', 'League Announcement'),
        
        # Division level events
        ('DIVISION_OPENING_DAY', 'Division Opening Day'),
        ('DIVISION_CLOSING_CEREMONY', 'Division Closing Ceremony'),
        ('DIVISION_CHAMPIONSHIP', 'Division Championship'),
        ('DIVISION_TOURNAMENT', 'Division Tournament'),
        ('DIVISION_CLINIC', 'Division Practice Clinic'),
        ('DIVISION_AWARDS', 'Division Awards Night'),
        ('DIVISION_ALLSTAR', 'Division All-Star Selection'),
        
        # Team level events
        ('TEAM_PRACTICE', 'Practice'),
        ('TEAM_GAME', 'Game'),
        ('TEAM_SCRIMMAGE', 'Scrimmage'),
        ('TEAM_HOME_OPENER', 'Home Opener'),
        ('TEAM_TOURNAMENT', 'Tournament'),
        ('TEAM_HANGOUT', 'Hangout/Social Event'),
        ('TEAM_PARTY', 'Team Party/Celebration'),
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
    
    # Scope hierarchy
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='TEAM')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    division = models.ForeignKey(Division, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='team_events')
    
    # Event details
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
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
            models.Index(fields=['scope', 'organization']),
            models.Index(fields=['scope', 'division']),
            models.Index(fields=['scope', 'team']),
            models.Index(fields=['event_type', 'status']),
            models.Index(fields=['date_time']),
        ]
    
    def __str__(self):
        scope_name = dict(self.SCOPE_CHOICES).get(self.scope, 'Unknown')
        target = self.organization or self.division or self.team
        return f"{target} - {self.get_event_type_display()} - {self.date_time.strftime('%m/%d/%Y')}"
    
    @property
    def is_completed(self):
        return self.status == 'COMPLETED'
    
    def propagate_to_teams(self):
        """
        Propagate organization and division events down to every team under them.
        """
        if self.scope == 'DIVISION' and self.division:
            teams = self.division.teams.all()
        elif self.scope == 'ORGANIZATION' and self.organization:
            teams = Team.objects.filter(division__season__organization=self.organization)
        else:
            return

        for team in teams:
            TeamEvent.objects.create(
                scope='TEAM',
                organization=team.division.season.organization,
                division=team.division,
                team=team,
                event_type=self.event_type,
                title=self.title,
                description=self.description,
                date_time=self.date_time,
                location=self.location,
                created_by=self.created_by,
                status=self.status,
                opponent_team=self.opponent_team,
                home_score=self.home_score,
                away_score=self.away_score,
                is_home_game=self.is_home_game,
                is_live=self.is_live,
                current_inning=self.current_inning,
                is_top_inning=self.is_top_inning,
                outs=self.outs,
                balls=self.balls,
                strikes=self.strikes,
                pitch_count=self.pitch_count,
                practice_focus=self.practice_focus,
                attendance_required=self.attendance_required,
                tournament_name=self.tournament_name,
                tournament_division=self.tournament_division,
            )

    def clean(self):
        """Validate scope hierarchy."""
        from django.core.exceptions import ValidationError
        
        if self.scope == 'ORGANIZATION' and not self.organization:
            raise ValidationError("Organization-level events require an organization.")
        if self.scope == 'DIVISION' and not self.division:
            raise ValidationError("Division-level events require a division.")
        if self.scope == 'TEAM' and not self.team:
            raise ValidationError("Team-level events require a team.")



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
    scoring_data = models.JSONField(default=dict, blank=True)

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

class ScoringToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='scoring_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Token for {self.game} (active: {self.is_active})"


class Alert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    division = models.ForeignKey(Division, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='alerts_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.organization}] {self.title}"


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