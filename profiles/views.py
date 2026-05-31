import csv
import io
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, FormView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.core.mail import send_mail

from django.views import View
from django.contrib.auth import authenticate, login
from django.db import transaction
from django.db.models import F
from django.contrib.auth.models import User
from django.apps import apps

from leagues.league_blueprints import LEAGUE_BLUEPRINTS
from .forms import OrganizationForm, SeasonForm, RosterImportForm, DivisionSetupForm, DivisionEditForm, TeamForm
from leagues.models import Division, Season, Team

import uuid  # For generating unique access codes for teams
from .models import Profile, Invitation, Player

class LandingPortalView(View):
    template_name = 'profiles/admin/landing_portal.html'

    def get(self, request):
        # Render the initial entry choices
        return render(request, self.template_name)

class PortalLoginView(View):
    def post(self, request):
        # Handle traditional user login paths
        user_str = request.POST.get('username')
        pass_str = request.POST.get('password')
        
        user = authenticate(request, username=user_str, password=pass_str)
        if user is not None:
            login(request, user)
            messages.success(request, f"Dugout session authenticated for {user.username}.")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password credentials.")
            return redirect('landing_portal')

class PortalRegisterOrgView(View):
    def post(self, request):
        # Handle atomic organization setup along with its administrator account
        org_name = request.POST.get('org_name')
        org_city = request.POST.get('org_city')
        org_state = request.POST.get('org_state')
        org_zip_code = request.POST.get('org_zip_code')

        adm_user = request.POST.get('admin_user')
        adm_email = request.POST.get('admin_email')
        adm_pass = request.POST.get('admin_pass')
        adm_first = request.POST.get('admin_first')
        adm_last = request.POST.get('admin_last')

        # Defensive validation checks
        if User.objects.filter(username=adm_user).exists():
            messages.error(request, f"The username '{adm_user}' is already registered.")
            return redirect('landing_portal')

        Organization = apps.get_model('leagues', 'Organization')

        with transaction.atomic():
            # 1. Create the new Organization model entry
            new_org = Organization.objects.create(name=org_name, city=org_city, state=org_state, zip_code=org_zip_code)
            
            # 2. Build the underlying Django Admin User
            new_admin = User.objects.create_user(
                username=adm_user, email=adm_email, password=adm_pass,
                first_name=adm_first, last_name=adm_last
            )
            
            # 3. Elevate their access profile role context immediately
            profile = new_admin.profile
            profile.role = 'ORG_OWNER'
            profile.organization = new_org
            profile.save()

            # Sign them in automatically on completion
            login(request, new_admin)

        messages.success(request, f"Ecosystem initialized successfully for '{new_org.name}'!")
        return redirect('dashboard')

class PortalVerifyTokenView(View):
    def get(self, request):
        # Handle passing token references directly to the REST API verification engine
        token_str = request.GET.get('token', '').strip()
        if not token_str:
            messages.error(request, "Please enter a valid invitation token pass code.")
            return redirect('landing_portal')
            
        # Re-route browser requests seamlessly directly into the Ninja verification route
        return redirect(f"/api/profiles/invitations/verify/{token_str}")


# DASHBOARD VIEW
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'profiles/admin/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.request.user.profile
        
        # Get the user's organization
        organization = profile.organization
        context['organization'] = organization

        if organization:
            # Toggle to include inactive seasons
            show_inactive = self.request.GET.get('show_inactive') in ['1', 'true', 'True']
            if show_inactive:
                seasons = organization.seasons.all().order_by('-year', '-season')
            else:
                seasons = organization.seasons.filter(is_active=True).order_by('-year', '-season')

            context['seasons'] = seasons
            context['has_seasons'] = seasons.exists()
            context['show_inactive'] = show_inactive
        else:
            context['has_seasons'] = False
            
        return context


# 1. STEP ONE: INITIALIZE ORGANIZATION
class CreateOrganizationView(LoginRequiredMixin, CreateView):
    template_name = 'profiles/admin/create_org.html'
    form_class = OrganizationForm
    
    def get_success_url(self):
        return reverse('dashboard')

    def form_valid(self, form):
        # Create the organization and link it to the user's profile
        self.object = form.save()
        profile = self.request.user.profile
        profile.role = 'ORG_OWNER'
        profile.organization = self.object
        profile.save()
        messages.success(self.request, "Organization established successfully!")
        return super().form_valid(form)

# 2. STEP TWO: SPAWN A SEASON
class CreateSeasonView(LoginRequiredMixin, CreateView):
    template_name = 'profiles/admin/create_season.html'
    form_class = SeasonForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('create_division', kwargs={'season_id': self.object.id})

    def form_valid(self, form):
        messages.success(self.request, "Season tracking window generated successfully!")
        return super().form_valid(form)

# 3. STEP THREE: DIVISION SETUP USING BLUEPRINT TEMPLATES
class CreateDivisionView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/create_division.html'
    form_class = DivisionSetupForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['season'] = get_object_or_404(Season, id=self.kwargs['season_id'])
        context['blueprints'] = LEAGUE_BLUEPRINTS
        return context

    def form_valid(self, form):
        season = get_object_or_404(Season, id=self.kwargs['season_id'])
        preset_type = form.cleaned_data['preset_type']
        notes = form.cleaned_data.get('notes', '').strip()
        created_divisions = []

        if preset_type == 'CUSTOM':
            division_name = form.cleaned_data['custom_name'].strip()
            division, created = apps.get_model('leagues', 'Division').objects.get_or_create(
                season=season,
                name=division_name,
                defaults={'preset_type': 'CUSTOM', 'notes': notes}
            )
            if created:
                created_divisions.append(division)
        else:
            for division_name in form.cleaned_data['selected_divisions']:
                blueprint = LEAGUE_BLUEPRINTS.get(preset_type, {})
                if division_name not in blueprint.get('divisions', []):
                    continue
                division, created = apps.get_model('leagues', 'Division').objects.get_or_create(
                    season=season,
                    name=division_name,
                    defaults={'preset_type': preset_type, 'notes': notes}
                )
                if created:
                    created_divisions.append(division)

        if created_divisions:
            names = ', '.join([d.name for d in created_divisions])
            messages.success(self.request, f"Created divisions for {season.name}: {names}.")
        else:
            messages.info(self.request, "No new divisions were created; matching divisions already exist.")

        return redirect('roster_onboarding', season_id=season.id)


class SeasonDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'profiles/admin/season_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        season = get_object_or_404(Season, id=self.kwargs['season_id'])
        divisions = Division.objects.filter(season=season).order_by('name')
        grouped = []

        for div in divisions:
            teams = Team.objects.filter(division=div).order_by('name')
            team_rows = []
            for team in teams:
                # Coach name fallback: first coach or empty
                coach_name = team.coaches.first()
                coach_label = coach_name.get_full_name() if coach_name else ''
                coach_count = team.coaches.count()
                player_count = team.playermembership_set.filter(is_active=True).count()
                fan_count = team.teammembership_set.filter(role='FOLLOWER', is_active=True).count()

                home_games = team.competition_home_games.filter(is_completed=True)
                away_games = team.competition_away_games.filter(is_completed=True)
                wins = home_games.filter(home_score__gt=F('away_score')).count() + away_games.filter(away_score__gt=F('home_score')).count()
                losses = home_games.filter(home_score__lt=F('away_score')).count() + away_games.filter(away_score__lt=F('home_score')).count()
                ties = home_games.filter(home_score=F('away_score')).count() + away_games.filter(away_score=F('home_score')).count()

                team_rows.append({
                    'team': team,
                    'coach_label': coach_label,
                    'coach_count': coach_count,
                    'player_count': player_count,
                    'fan_count': fan_count,
                    'record': f"{wins}-{losses}-{ties}",
                })

            grouped.append({'division': div, 'teams': team_rows})

        context['season'] = season
        context['grouped_divisions'] = grouped
        return context


class DivisionEditView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/edit_division.html'
    form_class = DivisionEditForm

    def get_initial(self):
        division = get_object_or_404(Division, id=self.kwargs['division_id'])
        return {
            'name': division.name,
            'preset_type': division.preset_type,
            'notes': division.notes or ''
        }

    def form_valid(self, form):
        division = get_object_or_404(Division, id=self.kwargs['division_id'])
        division.name = form.cleaned_data['name']
        division.preset_type = form.cleaned_data['preset_type']
        division.notes = form.cleaned_data.get('notes', '')
        division.save()
        messages.success(self.request, f"Updated division {division.name}.")
        return redirect('season_detail', season_id=division.season.id)
    
class CreateTeamView(LoginRequiredMixin, CreateView):
    template_name = 'profiles/admin/create_team.html'
    form_class = TeamForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped = []

        context['grouped_divisions'] = grouped
        return context
    
class TeamDetailView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/team_detail.html'
    form_class = TeamForm

    def get_initial(self):
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        return {
            'name': team.name,
            'color': team.color,
            'coaches': team.coaches.all(),
        }

    def form_valid(self, form):
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        team.name = form.cleaned_data['name']
        team.color = form.cleaned_data['color']
        team.coaches.set(form.cleaned_data['coaches'])
        team.save()
        messages.success(self.request, f"Updated team {team.name}.")
        return redirect('season_detail', season_id=team.season.id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = get_object_or_404(Team, id=self.kwargs['team_id'])

        # Coaches grouped by role
        coaches_qs = team.coaches.all()
        # Look up TeamMemberships for role info
        from profiles.models import TeamMembership, PlayerMembership
        memberships = TeamMembership.objects.filter(team=team, is_active=True)
        coaches = []
        for m in memberships.filter(role__in=['MANAGER', 'COACH']):
            user = m.user
            players = PlayerMembership.objects.filter(team=team, player__guardian=user)
            coaches.append({'membership': m, 'user': user, 'players': [p.player for p in players]})

        # Players on team
        players = PlayerMembership.objects.filter(team=team, is_active=True).select_related('player')
        player_count = players.count()

        manager_names = []
        assistant_names = []
        for m in memberships:
            full_name = m.user.get_full_name() or m.user.username
            if m.role == 'MANAGER':
                manager_names.append(full_name)
            elif m.role == 'COACH':
                assistant_names.append(full_name)

        home_completed = team.competition_home_games.filter(is_completed=True)
        away_completed = team.competition_away_games.filter(is_completed=True)
        wins = home_completed.filter(home_score__gt=F('away_score')).count() + away_completed.filter(away_score__gt=F('home_score')).count()
        losses = home_completed.filter(home_score__lt=F('away_score')).count() + away_completed.filter(away_score__lt=F('home_score')).count()
        ties = home_completed.filter(home_score=F('away_score')).count() + away_completed.filter(away_score=F('home_score')).count()

        # Fetch events: both legacy Games and new TeamEvents
        from competition.models import TeamEvent
        games_qs = team.competition_home_games.all() | team.competition_away_games.all()
        team_events = TeamEvent.objects.filter(team=team, event_type__in=['GAME', 'SCRIMMAGE'])
        
        # Combine and sort by date
        from itertools import chain
        all_events = list(chain(games_qs, team_events))
        all_events.sort(key=lambda x: x.date_time)
        events = all_events[:20]

        context['team'] = team
        context['coaches'] = coaches
        context['players'] = [pm.player for pm in players]
        context['player_count'] = player_count
        context['manager_names'] = manager_names
        context['coach_names'] = assistant_names
        context['record'] = {'wins': wins, 'losses': losses, 'ties': ties}
        context['events'] = events
        context['events_url'] = f'/competitions/team/{team.id}/events/'
        return context


class CreateCoachView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/create_coach.html'
    form_class = apps.get_model('profiles', 'TeamMembership') and None

    def get(self, request, *args, **kwargs):
        from .forms import TeamCoachForm
        form = TeamCoachForm()
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        return render(request, self.template_name, {'form': form, 'team': team})

    def post(self, request, *args, **kwargs):
        from .forms import TeamCoachForm
        form = TeamCoachForm(request.POST)
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        if form.is_valid():
            user = form.cleaned_data['user']
            role = form.cleaned_data['role']
            TeamMembership = apps.get_model('profiles', 'TeamMembership')
            TeamMembership.objects.get_or_create(user=user, team=team, role=role)
            messages.success(request, f"Added {role} {user.get_full_name() or user.username} to {team.name}.")
            return redirect('team_detail', team_id=team.id)
        return render(request, self.template_name, {'form': form, 'team': team})


class CreatePlayerView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/create_player.html'
    form_class = apps.get_model('profiles', 'Player') and None

    def get(self, request, *args, **kwargs):
        from .forms import PlayerCreateForm
        form = PlayerCreateForm()
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        return render(request, self.template_name, {'form': form, 'team': team})

    def post(self, request, *args, **kwargs):
        from .forms import PlayerCreateForm
        form = PlayerCreateForm(request.POST)
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        if form.is_valid():
            player = form.save(commit=False)
            guardian = form.cleaned_data.get('guardian')
            if guardian:
                player.guardian = guardian
            player.save()
            PlayerMembership = apps.get_model('profiles', 'PlayerMembership')
            PlayerMembership.objects.create(player=player, team=team, is_active=True)
            messages.success(request, f"Added player {player} to {team.name}.")
            return redirect('team_detail', team_id=team.id)
        return render(request, self.template_name, {'form': form, 'team': team})


class CreateGameView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/create_game.html'
    form_class = apps.get_model('profiles', 'Player') and None

    def get(self, request, *args, **kwargs):
        from .forms import GameCreateForm
        form = GameCreateForm()
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        return render(request, self.template_name, {'form': form, 'team': team})

    def post(self, request, *args, **kwargs):
        from .forms import GameCreateForm
        form = GameCreateForm(request.POST)
        team = get_object_or_404(Team, id=self.kwargs['team_id'])
        if form.is_valid():
            data = form.cleaned_data
            Game = apps.get_model('competition', 'Game')
            if data.get('is_home'):
                home_team = team
                away_team = None
            else:
                home_team = None
                away_team = team
            # Create a minimal opponent Team if name provided
            opponent_name = data.get('opponent_name')
            if opponent_name:
                Opponent = apps.get_model('leagues', 'Team')
                opponent = Opponent.objects.create(name=opponent_name, division=team.division, access_code='')
                if data.get('is_home'):
                    away_team = opponent
                else:
                    home_team = opponent

            Game.objects.create(season=team.season, home_team=home_team, away_team=away_team, date_time=data['date_time'], location=data['location'])
            messages.success(request, "Game created.")
            return redirect('team_detail', team_id=team.id)
        return render(request, self.template_name, {'form': form, 'team': team})

# 4. STEP FOUR: BULK ROSTER / STAFF IMPORT GATEWAY
class RosterOnboardingView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/roster_onboarding.html'
    form_class = RosterImportForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['season'] = get_object_or_404(Season, id=self.kwargs['season_id'])
        return context

    def form_valid(self, form):
        import secrets
        import string
        from leagues.models import Division, Team
        
        season = get_object_or_404(Season, id=self.kwargs['season_id'])
        
        division_name = form.cleaned_data.get('division_name').strip()
        team_name = form.cleaned_data.get('team_name').strip()
        manual_email = form.cleaned_data.get('manual_email')
        manual_first = form.cleaned_data.get('manual_first_name')
        manual_last = form.cleaned_data.get('manual_last_name')

        with transaction.atomic():
            # 1. Resolve or spawn the Division tier for this season context safely
            division, _ = Division.objects.get_or_create(
                season=season,
                name=division_name
            )

            # 2. Build the alphanumeric clean 6-character shortcode for fan apps
            allowed_chars = string.ascii_uppercase + string.digits
            unique_code = ''.join(secrets.choice(allowed_chars) for _ in range(6))
            while Team.objects.filter(access_code=unique_code).exists():
                unique_code = ''.join(secrets.choice(allowed_chars) for _ in range(6))

            # 3. Auto-resolve target team inside that specific division context
            team, _ = Team.objects.get_or_create(
                name=team_name,
                division=division,
                defaults={'access_code': unique_code}
            )

        # Process Manual Record
        if manual_email:
            self._process_coach_onboarding(manual_email, manual_first, manual_last, team)

        # Process Spreadsheet Upload
        csv_file = self.request.FILES.get('spreadsheet_file')
        if csv_file:
            file_data = csv_file.read().decode("utf-8")
            io_string = io.StringIO(file_data)
            reader = csv.DictReader(io_string)
            
            for row in reader:
                email = row.get('email', '').strip()
                first = row.get('first_name', '').strip()
                last = row.get('last_name', '').strip()
                if email:
                    self._process_coach_onboarding(email, first, last, team)

        messages.success(self.request, f"Roster invitations processed for the {team.name} in division {division.name}!")
        return redirect('roster_onboarding', season_id=season.id)

    def _process_coach_onboarding(self, email, first_name, last_name, team):
        """Helper to seamlessly bind invitation row logic and trigger email backends."""
        invitation, created = Invitation.objects.get_or_create(
            email=email.lower().strip(),
            team=team,
            target_role='COACH',
            invited_by=self.request.user,
            is_accepted=False
        )
        
        invite_url = self.request.build_absolute_uri(f"/api/profiles/invitations/verify/{invitation.token}")
        
        # Print block acting as local fallback stream out to your console logs
        print("\n" + "="*60)
        print(f"COACH ONBOARDING INVITATION DEEP-LINK GENERATED")
        print(f"To: {email} ({first_name} {last_name})")
        print(f"Team: {team.name} ({team.division.name})")
        print(f"URL: {invite_url}")
        print("="*60 + "\n")
