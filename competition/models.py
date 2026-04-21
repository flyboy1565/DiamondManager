import uuid
from django.db import models
from leagues.models import Team, Season

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
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} - {self.date_time.strftime('%m/%d')}"

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