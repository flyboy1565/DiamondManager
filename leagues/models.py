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
    access_code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name
