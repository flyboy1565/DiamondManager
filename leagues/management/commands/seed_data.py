import uuid
import random
import datetime
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from faker import Faker

from leagues.models import Organization, Season, Division, Team
from profiles.models import TeamMembership, Player, PlayerMembership
from competition.models import Game, GameLineupEntry


DEFAULT_PASSWORD = 'password123'
DEMO_ORG_NAME = 'Canyon Creek Little League'


def generate_unique_team_code():
    return uuid.uuid4().hex[:6].upper()


class Command(BaseCommand):
    help = 'Seed sample data plus a reproducible demo team (coach/scorer/parent + games today/tomorrow/Saturday).'

    def handle(self, *args, **options):
        fake = Faker()
        Faker.seed(42)
        random.seed(42)

        already_seeded = Organization.objects.filter(name='Phoenix Bombers Baseball').exists()
        if already_seeded:
            self.stdout.write('Bulk sample data already present; skipping random seeding.')
        else:
            self._seed_random(fake)

        self._ensure_demo()

        self.stdout.write(self.style.SUCCESS('Database seeding completed!'))

    # ------------------------------------------------------------------
    # Random sample data
    # ------------------------------------------------------------------
    def _seed_random(self, fake):
        # Create users with profile roles
        users = []
        for i in range(20):
            user = User.objects.create_user(
                username=f'{fake.user_name()}_{i}',
                password=DEFAULT_PASSWORD,
            )
            user.email = f'user{i}@example.com'
            user.save()
            user.profile.role = random.choice(['COACH', 'PARENT', 'ORG_OWNER'])
            user.profile.save()
            users.append(user)
            self.stdout.write(f'  Created user: {user.username}')

        # Create seasons with divisions and teams
        division_pool = ['8U', '10U', '12U', 'Majors']
        team_names_pool = ['Bombers', 'Eagles', 'Vipers', 'Lions', 'Tigers', 'Bears', 'Sharks', 'Wolves']
        teams = []
        for org_name in ['Phoenix Bombers Baseball', 'Desert Eagles', 'Valley Vipers', 'Mountain Lions']:
            org = Organization.objects.create(name=org_name)
            season = Season.objects.create(
                organization=org,
                season='Spring',
                year=fake.year(),
                is_active=True,
            )
            self.stdout.write(f'Created season: {season.name} for {org.name}')

            for div_name in random.sample(division_pool, 2):
                division = Division.objects.create(
                    season=season,
                    name=div_name,
                    preset_type='AGE_BRACKET',
                    notes=fake.sentence(nb_words=8),
                    allowed_positions=["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "UTL"],
                )
                for _ in range(random.randint(1, 2)):
                    team = Team.objects.create(
                        name=f'{fake.city().split()[0]} {random.choice(team_names_pool)}',
                        division=division,
                        color=fake.color_name(),
                        access_code=generate_unique_team_code(),
                    )
                    teams.append(team)
                    self.stdout.write(f'    Created team: {team.name}')

        available_coaches = [u for u in users if u.profile.role in ['COACH', 'ORG_OWNER']]
        available_parents = [u for u in users if u.profile.role == 'PARENT']
        for team in teams:
            for coach in random.sample(available_coaches, min(2, len(available_coaches))):
                TeamMembership.objects.create(user=coach, team=team, role='COACH', is_active=True)
            for parent in random.sample(available_parents, min(5, len(available_parents))):
                TeamMembership.objects.create(user=parent, team=team, role='PARENT', is_active=True)

        for team in teams:
            team_parents = [m.user for m in TeamMembership.objects.filter(team=team, role='PARENT')]
            for _ in range(random.randint(8, 12)):
                guardian = random.choice(team_parents) if team_parents else None
                player = Player.objects.create(
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    date_of_birth_field=fake.date_of_birth(minimum_age=8, maximum_age=14),
                    guardian=guardian,
                )
                PlayerMembership.objects.create(
                    player=player,
                    team=team,
                    jersey_number=str(random.randint(1, 99)),
                    is_active=True,
                )

        for season in Season.objects.all():
            season_teams = list(Team.objects.filter(division__season=season))
            if len(season_teams) < 2:
                continue
            for _ in range(random.randint(5, 10)):
                home_team, away_team = random.sample(season_teams, 2)
                Game.objects.create(
                    season=season,
                    home_team=home_team,
                    away_team=away_team,
                    date_time=timezone.now() + timedelta(days=random.randint(1, 30)),
                    location=f'{fake.city()} Field {random.randint(1, 5)}',
                )

    # ------------------------------------------------------------------
    # Reproducible demo scenario
    # ------------------------------------------------------------------
    def _ensure_demo(self):
        org, _ = Organization.objects.get_or_create(name=DEMO_ORG_NAME)
        season, _ = Season.objects.get_or_create(
            organization=org,
            season='Fall',
            year=timezone.now().year,
            defaults={'is_active': True},
        )
        allowed = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "UTL"]
        division, _ = Division.objects.get_or_create(
            season=season,
            name='Majors',
            defaults={'preset_type': 'AGE_BRACKET', 'allowed_positions': allowed},
        )
        eagles, _ = Team.objects.get_or_create(
            division=division, name='Canyon Creek Eagles',
            defaults={'color': 'Green', 'access_code': 'LWIBMX'},
        )
        thunder, _ = Team.objects.get_or_create(
            division=division, name='Canyon Creek Thunder',
            defaults={'color': 'Blue', 'access_code': 'S8P0MF'},
        )
        mustangs, _ = Team.objects.get_or_create(
            division=division, name='Canyon Creek Mustangs',
            defaults={'color': 'Red', 'access_code': '5XGMJQ'},
        )

        def ensure_user(username, role):
            user, _ = User.objects.get_or_create(username=username)
            user.email = f'{username}@example.com'
            user.set_password(DEFAULT_PASSWORD)
            user.save()
            profile = user.profile
            profile.role = role
            profile.organization = org
            profile.save()
            return user

        owner = ensure_user('owner', 'ORG_OWNER')
        coach = ensure_user('coach_mike', 'COACH')
        scorer = ensure_user('scorer', 'SCORER')
        parent = ensure_user('parent', 'PARENT')

        for user, role in [
            (owner, 'ORG_ADMIN'),
            (coach, 'COACH'),
            (scorer, 'SCORER'),
            (parent, 'PARENT'),
        ]:
            TeamMembership.objects.update_or_create(
                user=user, team=eagles, defaults={'role': role, 'is_active': True},
            )

        # Parent with a child on the team
        child, _ = Player.objects.get_or_create(
            first_name='Sam', last_name='Demo', guardian=parent,
            defaults={'date_of_birth_field': date(2016, 5, 1)},
        )
        PlayerMembership.objects.update_or_create(
            player=child, team=eagles, defaults={'jersey_number': '7', 'is_active': True},
        )

        # Games: today, tomorrow, and this coming Saturday
        today = timezone.localdate()
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        schedule = [
            (today, thunder, '18:00'),
            (today + timedelta(days=1), mustangs, '10:00'),
            (saturday, thunder, '10:00'),
        ]
        for day, opponent, hhmm in schedule:
            dt = timezone.make_aware(
                datetime.datetime.combine(day, datetime.datetime.strptime(hhmm, '%H:%M').time())
            )
            game, created = Game.objects.get_or_create(
                season=season, home_team=eagles, away_team=opponent, date_time=dt,
                defaults={'location': 'Canyon Creek Field 1'},
            )
            self._ensure_lineup(game, eagles)
            self._ensure_lineup(game, opponent)
            self.stdout.write(
                f'  {"Created" if created else "Ensured"} game: '
                f'{eagles.name} vs {opponent.name} on {day} {hhmm}'
            )

    def _ensure_lineup(self, game, team):
        if GameLineupEntry.objects.filter(game=game, team=team).exists():
            return
        players = list(PlayerMembership.objects.filter(team=team, is_active=True))
        for order, membership in enumerate(players[:9], 1):
            GameLineupEntry.objects.create(
                game=game,
                team=team,
                player=players[order - 1].player,
                batting_order=order,
                position='DH',
                is_active=True,
            )
