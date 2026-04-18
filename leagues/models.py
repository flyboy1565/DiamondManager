import uuid
from django.db import models
from django.contrib.auth.models import User

class SeasonType(models.TextChoices):
    SPRING = 'Spring', 'Spring'
    SUMMER = 'Summer', 'Summer'
    FALL = 'Fall', 'Fall'
    WINTER = 'Winter', 'Winter'

class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=10)

    def __str__(self):
        return self.name

class Season(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='seasons')
    season = models.CharField(max_length=10, choices=SeasonType.choices)
    year = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    @property
    def name(self):
        return f"{self.season}-{self.year}"

    def __str__(self):
        return f"{self.organization.name} - {self.name}"

class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=50, blank=True)
    coaches = models.ManyToManyField(User, related_name='coaching_teams')
    icon = models.ImageField(upload_to='team_icons/', null=True, blank=True)

    def __str__(self):
        return self.name

class Player(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    jersey_number = models.PositiveIntegerField(null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to='player_images/', null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"        

class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_games')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_games')
    date_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    home_score = models.PositiveIntegerField(default=0)
    away_score = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)

class PlayerGameStat(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='stats')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='player_stats')
    # Example stats - you can expand these based on the sport
    at_bats = models.PositiveIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0)
    runs = models.PositiveIntegerField(default=0)
    rbi = models.PositiveIntegerField(default=0)        
