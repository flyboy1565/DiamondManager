import random
import uuid
from datetime import date

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from faker import Faker

from leagues.models import Organization, Season, Division, Team
from profiles.models import Profile, TeamMembership, Player, PlayerMembership


def generate_unique_team_code():
    for _ in range(20):
        code = uuid.uuid4().hex[:8].upper()
        if not Team.objects.filter(access_code=code).exists():
            return code
    raise RuntimeError('Unable to generate unique access code for team.')


def create_user(role, organization=None, prefix='user'):
    fake = Faker()
    username = f"{prefix}_{fake.user_name()}_{random.randint(1000,9999)}"
    user = User.objects.create_user(
        username=username,
        email=fake.email(),
        first_name=fake.first_name(),
        last_name=fake.last_name(),
        password='password123'
    )
    profile = user.profile
    profile.role = role
    profile.organization = organization
    profile.save()
    return user


class Command(BaseCommand):
    help = 'Seed additional sample data into the database for organizations, seasons, divisions, teams, and players.'

    def handle(self, *args, **options):
        fake = Faker()
        Faker.seed(42)
        random.seed(42)

        self.stdout.write(self.style.NOTICE('Starting additional seed data process...'))

        existing_org_count = Organization.objects.count()
        self.stdout.write(f'Existing organizations: {existing_org_count}')

        # Prepare organization names that do not collide with existing records.
        base_org_names = [
            'Riverbend Little League',
            'Maple Grove Little League',
            'Sunset Valley Little League',
            'North Ridge Little League',
            'Pine Hill Little League'
        ]
        used_org_names = set(Organization.objects.values_list('name', flat=True))
        org_names = [name for name in base_org_names if name not in used_org_names][:3]

        if len(org_names) < 3:
            self.stdout.write(self.style.WARNING('Not enough unique organization names found. Generating additional names.'))
            while len(org_names) < 3:
                candidate = f"{fake.city()} Little League"
                if candidate not in used_org_names and candidate not in org_names:
                    org_names.append(candidate)

        created_orgs = []
        with transaction.atomic():
            for org_name in org_names:
                org = Organization.objects.create(
                    name=org_name,
                    city=fake.city(),
                    state=fake.state_abbr(),
                    zip_code=fake.zipcode()
                )
                created_orgs.append(org)
                self.stdout.write(self.style.SUCCESS(f'Created organization: {org.name}'))

                # Create an org owner and a couple of admin/coach users for this org.
                owner = create_user('ORG_OWNER', organization=org, prefix='owner')
                admins = [create_user('ORG_ADMIN', organization=org, prefix='admin') for _ in range(1)]
                coaches = [create_user('COACH', organization=org, prefix='coach') for _ in range(4)]
                parents = [create_user('PARENT', organization=org, prefix='parent') for _ in range(15)]

                # Create a current season plus one or two previous seasons.
                year = date.today().year
                season_names = [
                    ('Spring', year - 2),
                    ('Summer', year - 1),
                    ('Spring', year),
                ]
                seasons = []
                for season_label, season_year in season_names:
                    season = Season.objects.create(
                        organization=org,
                        season=season_label,
                        year=season_year,
                        is_active=(season_year == year)
                    )
                    seasons.append(season)
                    self.stdout.write(f'  Created season: {season.name}')

                division_names = ['8U', '10U', '12U', 'Majors']
                for season in seasons:
                    for division_name in division_names[:random.randint(3, 4)]:
                        division = Division.objects.create(
                            season=season,
                            name=division_name,
                            preset_type='LITTLE_LEAGUE',
                            notes=fake.sentence(nb_words=8)
                        )
                        self.stdout.write(f'    Created division: {division.name} ({season.name})')

                        team_count = random.randint(4, 8)
                        for _ in range(team_count):
                            team_name = f"{fake.color_name().title()} {random.choice(['Aces', 'Tigers', 'Knights', 'Stars', 'Rockets', 'Sharks'])}"
                            team = Team.objects.create(
                                name=team_name,
                                division=division,
                                color=fake.color_name(),
                                access_code=generate_unique_team_code()
                            )

                            self.stdout.write(f'      Created team: {team.name}')

                            # Assign coaches to the team.
                            team_coaches = random.sample(coaches, min(len(coaches), 2))
                            for coach in team_coaches:
                                team.coaches.add(coach)
                                TeamMembership.objects.get_or_create(
                                    user=coach,
                                    team=team,
                                    role='COACH',
                                    is_active=True
                                )

                            # Create players for the team.
                            player_count = random.randint(9, 15)
                            team_guardians = random.sample(parents, min(len(parents), max(5, player_count)))
                            for player_index in range(player_count):
                                guardian = random.choice(team_guardians)
                                player = Player.objects.create(
                                    first_name=fake.first_name(),
                                    last_name=fake.last_name(),
                                    date_of_birth_field=fake.date_of_birth(minimum_age=8, maximum_age=14),
                                    guardian=guardian
                                )
                                PlayerMembership.objects.create(
                                    player=player,
                                    team=team,
                                    jersey_number=str(random.randint(1, 99)),
                                    is_active=True
                                )
                                self.stdout.write(f'        Created player: {player.first_name} {player.last_name}')

        self.stdout.write(self.style.SUCCESS('Additional seed data complete.'))
        self.stdout.write(f'Created {len(created_orgs)} new organizations with seasons, divisions, teams, and players.')
