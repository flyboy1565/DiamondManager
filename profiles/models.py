from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
import uuid

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class Profile(models.Model):
    # This links the Profile to the default Django User
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Standard Role definitions
    ROLE_CHOICES = [
        ('ADMIN', 'Global Admin'),
        ('ORG_OWNER', 'Organization Owner'),
        ('ORG_ADMIN', 'Organization Admin'),
        ('MANAGER', 'Team Manager'),
        ('COACH', 'Team Coach'),
        ('SCORER', 'Official Scorer'),
        ('PARENT', 'Player Parent'),
        ('FOLLOWER', 'Player Follower'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='FOLLOWER')
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class TeamMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    team = models.ForeignKey('leagues.Team', on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Profile.ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevents duplicate roles on the same team
        unique_together = ('user', 'team', 'role')    

class Player(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    date_of_birth_field = models.DateField(null=True, blank=True)
    
    # The "Primary Contact" - usually the parent who created the profile
    guardian = models.ForeignKey(User, on_delete=models.CASCADE, related_name='players')

    @property
    def date_of_birth(self):
        return self.date_of_birth_field.isoformat() if self.date_of_birth_field else None

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class PlayerMembership(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='team_history')
    team = models.ForeignKey('leagues.Team', on_delete=models.CASCADE)
    jersey_number = models.CharField(max_length=5, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def team_name(self):
        return self.team.name
    
    class Meta:
        unique_together = ('player', 'team')        