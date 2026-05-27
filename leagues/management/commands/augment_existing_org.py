import random
import uuid
from datetime import date

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
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
    help = 'Augment existing organization data with seasons, divisions, teams, and players.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-name', type=str, help='Name of the existing organization to augment.')
        parser.add_argument('--organization-id', type=str, help='UUID of the existing organization to augment.')
        parser.add_argument('--all', action='store_true', help='Augment all existing organizations.')
        parser.add_argument('--teams-per-division', type=int, default=6, help='Target number of teams per division.')
        parser.add_argument('--players-per-team', type=int, default=12, help='Target number of players per team.')
        parser.add_argument('--divisions', type=int, default=4, help='Target number of divisions to create per season.')

    def handle(self, *args, **options):
        fake = Faker()
        Faker.seed(42)
        random.seed(42)

        org_name = options.get('organization_name')
        org_id = options.get('organization_id')
        augment_all = options.get('all')
        team_target = options.get('teams_per_division')
        player_target = options.get('players_per_team')
        division_target = options.get('divisions')

        if not augment_all and not org_name and not org_id:
            self.stdout.write(self.style.ERROR('Please specify --organization-name, --organization-id, or --all.'))
            return

        orgs = Organization.objects.none()
        if augment_all:
            orgs = Organization.objects.all()
        elif org_id:
            orgs = Organization.objects.filter(id=org_id)
        elif org_name:
            orgs = Organization.objects.filter(name__iexact=org_name)

        if not orgs.exists():
            self.stdout.write(self.style.ERROR('No matching organizations found.'))
            return

        self.stdout.write(self.style.NOTICE(f'Augmenting {orgs.count()} organization(s).'))

        target_division_names = ['8U', '10U', '12U', 'Majors'][:division_target]
        year = date.today().year
        season_plan = [
            ('Spring', year - 2),
            ('Summer', year - 1),
            ('Spring', year),
        ]

        for org in orgs:
            self.stdout.write(self.style.SUCCESS(f'Processing organization: {org.name}'))
            org_coaches = list(User.objects.filter(profile__organization=org, profile__role__in=['COACH', 'ORG_ADMIN', 'ORG_OWNER']))
            org_parents = list(User.objects.filter(profile__organization=org, profile__role='PARENT'))

            if len(org_coaches) < 4:
                needed = 4 - len(org_coaches)
                for _ in range(needed):
                    coach = create_user('COACH', organization=org, prefix='coach')
                    org_coaches.append(coach)
                    self.stdout.write(f'  Created coach user: {coach.username}')

            if len(org_parents) < 12:
                needed = 12 - len(org_parents)
                for _ in range(needed):
                    parent = create_user('PARENT', organization=org, prefix='parent')
                    org_parents.append(parent)
                    self.stdout.write(f'  Created parent user: {parent.username}')

            with transaction.atomic():
                for season_label, season_year in season_plan:
                    season, created = Season.objects.get_or_create(
                        organization=org,
                        season=season_label,
                        year=season_year,
                        defaults={'is_active': season_year == year}
                    )
                    if created:
                        self.stdout.write(f'  Created season: {season.name}')
                    else:
                        self.stdout.write(f'  Found season: {season.name}')

                    for division_name in target_division_names:
                        division, created_div = Division.objects.get_or_create(
                            season=season,
                            name=division_name,
                            defaults={
                                'preset_type': 'LITTLE_LEAGUE',
                                'notes': fake.sentence(nb_words=10)
                            }
                        )
                        if created_div:
                            self.stdout.write(f'    Created division: {division.name}')
                        else:
                            self.stdout.write(f'    Found division: {division.name}')

                        existing_team_count = division.teams.count()
                        if existing_team_count < team_target:
                            for _ in range(team_target - existing_team_count):
                                team_name = f"{fake.color_name().title()} {random.choice(['Aces', 'Tigers', 'Knights', 'Stars', 'Rockets', 'Sharks', 'Hawks'])}"
                                team = Team.objects.create(
                                    name=team_name,
                                    division=division,
                                    color=fake.color_name(),
                                    access_code=generate_unique_team_code()
                                )
                                self.stdout.write(f'      Created team: {team.name}')

                                team_coaches = random.sample(org_coaches, min(2, len(org_coaches)))
                                for coach in team_coaches:
                                    team.coaches.add(coach)
                                    TeamMembership.objects.get_or_create(
                                        user=coach,
                                        team=team,
                                        role='COACH',
                                        is_active=True
                                    )

                                player_count = player_target
                                guardians = random.sample(org_parents, min(len(org_parents), max(5, player_count)))
                                for _ in range(player_count):
                                    guardian = random.choice(guardians)
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
                        else:
                            self.stdout.write(f'      Division already has {existing_team_count} teams; no new teams created.')

        self.stdout.write(self.style.SUCCESS('Existing organization augmentation complete.'))
