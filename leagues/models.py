import uuid
from django.db import models
from django.contrib.auth.models import User

from .fields import EncryptedTextField


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
    max_events_per_team_per_week = models.PositiveIntegerField(default=10, help_text="Maximum number of countable events a team can have in a Mon-Sun week")

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

    @property
    def teams(self):
        return Team.objects.filter(division__season=self)

    def __str__(self):
        return f"{self.organization.name} - {self.name}"

class Division(models.Model):
    LEAGUE_PRESETS = [
        ('CUSTOM', 'Custom Rules / Independent'),
        ('LITTLE_LEAGUE', 'Little League Baseball'),
        ('CAL_RIPKEN', 'Cal Ripken Baseball'),
        ('BABE_RUTH', 'Babe Ruth Baseball'),
        ('AGE_BRACKET', 'Age Bracketed (10U, 12U, etc.)'),
    ]

    season = models.ForeignKey('Season', on_delete=models.CASCADE, related_name='divisions')
    name = models.CharField(max_length=100, help_text="e.g., 12U, 10U, Majors")
    preset_type = models.CharField(
        max_length=20,
        choices=LEAGUE_PRESETS,
        default='CUSTOM',
        verbose_name="League Rule Preset"
    )
    notes = models.TextField(blank=True, null=True)
    allowed_positions = models.JSONField(default=list, blank=True,
        help_text="Valid defensive positions for this division. Empty = use defaults.")

    class Meta:
        unique_together = ('season', 'name')

    def __str__(self):
        return f"{self.name} ({self.get_preset_type_display()})"

    @property
    def organization(self):
        return self.season.organization


class Facility(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='facilities')
    name = models.CharField(max_length=255, help_text="Facility or school name")
    address = models.CharField(max_length=255, blank=True, help_text="Street address, city, state, zip")
    field_name = models.CharField(max_length=255, blank=True, help_text="e.g. Field 1, North Field, Main Diamond")
    notes = models.TextField(blank=True, help_text="Parking instructions, gate codes, etc.")

    class Meta:
        verbose_name_plural = "facilities"
        ordering = ['name', 'field_name']

    def __str__(self):
        label = self.name
        if self.field_name:
            label += f" \u2014 {self.field_name}"
        if self.address:
            label += f" ({self.address})"
        return label


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Pivot from Season to Division
    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name='teams')
    
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=50, blank=True)
    coaches = models.ManyToManyField(User, related_name='coaching_teams')
    icon = models.ImageField(upload_to='team_icons/', null=True, blank=True)
    access_code = models.CharField(max_length=20, unique=True)

    # Clean shortcut property to easily look up the season or organization up the chain
    @property
    def season(self):
        return self.division.season

    def __str__(self):
        return f"{self.name} ({self.division.name})"
class OrganizationYouTubeConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="youtube_config")
    youtube_channel_id = models.CharField(max_length=100, blank=True, help_text="YouTube Channel ID (e.g., UC...)")
    youtube_client_id = models.CharField(max_length=255, blank=True)
    youtube_client_secret = EncryptedTextField(blank=True, help_text="Encrypted at rest")
    youtube_refresh_token = EncryptedTextField(blank=True, help_text="Encrypted at rest")
    streaming_server_srt_url = models.CharField(max_length=255, blank=True, help_text="SRT base URL e.g. srt://relay.example.com:10080")
    privacy_status = models.CharField(
        max_length=20,
        choices=[("public", "Public"), ("unlisted", "Unlisted"), ("private", "Private")],
        default="unlisted",
    )
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"YouTube Config - {self.organization.name}"
