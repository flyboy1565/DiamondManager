import uuid
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from faker import Faker

from leagues.models import Organization, Season, Division, Team
from profiles.models import TeamMembership, Player, PlayerMembership
from competition.models import Game, GameLineupEntry


def generate_unique_team_code():
    for _ in range(20):
        code = uuid.uuid4().hex[:8].upper()
        if not Team.objects.filter(access_code=code).exists():
            return code
    raise RuntimeError('Unable to generate unique access code for team.')


class Command(BaseCommand):
    help = 'Seed the database with sample data for testing'

    def handle(self, *args, **options):
        fake = Faker()
        Faker.seed(42)
        random.seed(42)

        self.stdout.write('Seeding database...')

        # Create organizations
        org_names = ['Phoenix Bombers Baseball', 'Desert Eagles', 'Valley Vipers', 'Mountain Lions']
        organizations = []
        for name in org_names:
            org = Organization.objects.create(
                name=name,
                city=fake.city(),
                state=fake.state_abbr(),
                zip_code=fake.zipcode()
            )
            organizations.append(org)
            self.stdout.write(f'Created organization: {org.name}')

        # Create users with profiles
        roles = ['COACH', 'PARENT', 'ORG_OWNER']
        users = []
        for i in range(20):
            username = f"{fake.user_name()}_{i}"
            user = User.objects.create_user(
                username=username,
                email=fake.email(),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                password='password123'
            )

            profile = user.profile
            profile.role = random.choice(roles)
            profile.phone_number = fake.phone_number()
            profile.save()

            users.append(user)
            self.stdout.write(f'Created user: {user.username} ({profile.role})')

        # Create seasons with divisions
        division_pool = ['8U', '10U', '12U', 'Majors']
        teams = []
        for org in organizations:
            season = Season.objects.create(
                organization=org,
                season='Spring',
                year=fake.year(),
                is_active=True
            )
            self.stdout.write(f'Created season: {season.name} for {org.name}')

            # Create 2 divisions per season
            for div_name in random.sample(division_pool, 2):
                division = Division.objects.create(
                    season=season,
                    name=div_name,
                    preset_type='AGE_BRACKET',
                    notes=fake.sentence(nb_words=8),
                    allowed_positions=["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "UTL"]
                )
                self.stdout.write(f'  Created division: {division.name}')

                # Create 1-2 teams per division (matches original 2-4 teams per season)
                team_names_pool = ['Bombers', 'Eagles', 'Vipers', 'Lions', 'Tigers', 'Bears', 'Sharks', 'Wolves']
                for _ in range(random.randint(1, 2)):
                    team = Team.objects.create(
                        name=f'{fake.city().split()[0]} {random.choice(team_names_pool)}',
                        division=division,
                        color=fake.color_name(),
                        access_code=generate_unique_team_code()
                    )
                    teams.append(team)
                    self.stdout.write(f'    Created team: {team.name}')

        # Create team memberships (coaches and parents)
        coaches_per_team = 2
        parents_per_team = 5

        for team in teams:
            available_coaches = [u for u in users if u.profile.role in ['COACH', 'ORG_OWNER']]
            coaches = random.sample(available_coaches, min(coaches_per_team, len(available_coaches)))

            for coach in coaches:
                TeamMembership.objects.create(
                    user=coach,
                    team=team,
                    role='COACH',
                    is_active=True
                )
                self.stdout.write(f'  Added coach {coach.username} to {team.name}')

            available_parents = [u for u in users if u.profile.role == 'PARENT']
            parents = random.sample(available_parents, min(parents_per_team, len(available_parents)))

            for parent in parents:
                TeamMembership.objects.create(
                    user=parent,
                    team=team,
                    role='PARENT',
                    is_active=True
                )
                self.stdout.write(f'  Added parent {parent.username} to {team.name}')

        # Create players
        players = []
        for team in teams:
            num_players = random.randint(8, 12)
            team_parents = [m.user for m in TeamMembership.objects.filter(team=team, role='PARENT')]

            for i in range(num_players):
                guardian = random.choice(team_parents) if team_parents else random.choice(
                    [u for u in users if u.profile.role == 'PARENT'])

                player = Player.objects.create(
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    date_of_birth_field=fake.date_of_birth(minimum_age=8, maximum_age=14),
                    guardian=guardian
                )
                players.append(player)

                PlayerMembership.objects.create(
                    player=player,
                    team=team,
                    jersey_number=str(random.randint(1, 99)),
                    is_active=True
                )

                self.stdout.write(f'  Created player: {player.first_name} {player.last_name} for {team.name}')

        # Create some games
        for season in Season.objects.all():
            season_teams = list(Team.objects.filter(division__season=season))
            if len(season_teams) >= 2:
                num_games = random.randint(5, 10)
                for i in range(num_games):
                    home_team, away_team = random.sample(season_teams, 2)
                    game = Game.objects.create(
                        season=season,
                        home_team=home_team,
                        away_team=away_team,
                        date_time=timezone.now() + timedelta(days=random.randint(1, 30)),
                        location=f'{fake.city()} Field {random.randint(1, 5)}',
                        home_score=random.randint(0, 8),
                        away_score=random.randint(0, 8),
                        is_completed=random.choice([True, False]),
                        is_live=random.choice([True, False]) if not random.choice([True, False]) else False,
                        current_inning=random.randint(1, 7) if random.choice([True, False]) else 1,
                        is_top_inning=random.choice([True, False]),
                        outs=random.randint(0, 2),
                        balls=random.randint(0, 3),
                        strikes=random.randint(0, 2),
                        pitch_count=random.randint(20, 100)
                    )

                    # Create lineup for this game
                    home_players = list(PlayerMembership.objects.filter(team=home_team, is_active=True))
                    away_players = list(PlayerMembership.objects.filter(team=away_team, is_active=True))

                    for i, pm in enumerate(home_players[:9], 1):
                        GameLineupEntry.objects.create(
                            game=game,
                            team=home_team,
                            player=pm.player,
                            batting_order=i,
                            position=random.choice(['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF']),
                            is_active=True
                        )

                    for i, pm in enumerate(away_players[:9], 1):
                        GameLineupEntry.objects.create(
                            game=game,
                            team=away_team,
                            player=pm.player,
                            batting_order=i,
                            position=random.choice(['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF']),
                            is_active=True
                        )

                    self.stdout.write(f'  Created game: {home_team.name} vs {away_team.name} with lineups')

        self.stdout.write(self.style.SUCCESS('Database seeding completed!'))
