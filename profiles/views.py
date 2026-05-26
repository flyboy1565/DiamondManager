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
from django.contrib.auth.models import User
from django.apps import apps

from leagues.models import Team, Season  # Assuming where leagues apps reside
from .models import Profile, Invitation, Player
from .forms import OrganizationForm, SeasonForm, RosterImportForm

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
            # Get all seasons for this organization
            seasons = organization.seasons.all().order_by('-year', '-season')
            context['seasons'] = seasons
            context['has_seasons'] = seasons.exists()
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
        response = super().form_valid(self.object)
        profile = self.request.user.profile
        profile.role = 'ORG_OWNER'
        profile.organization = self.object
        profile.save()
        messages.success(self.request, "Organization established successfully!")
        return response

# 2. STEP TWO: SPAWN A SEASON
class CreateSeasonView(LoginRequiredMixin, CreateView):
    template_name = 'profiles/admin/create_season.html'
    form_class = SeasonForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('roster_onboarding', kwargs={'season_id': self.object.id})

    def form_valid(self, form):
        messages.success(self.request, "Season tracking window generated successfully!")
        return super().form_valid(form)

# 3. STEP THREE: BULK ROSTER / STAFF IMPORT GATEWAY
class RosterOnboardingView(LoginRequiredMixin, FormView):
    template_name = 'profiles/admin/roster_onboarding.html'
    form_class = RosterImportForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['season'] = get_object_or_404(Season, id=self.kwargs['season_id'])
        return context

    def form_valid(self, form):
        season = get_object_or_404(Season, id=self.kwargs['season_id'])
        
        # Pull manual row if filled
        manual_email = form.cleaned_data.get('manual_email')
        manual_first = form.cleaned_data.get('manual_first_name')
        manual_last = form.cleaned_data.get('manual_last_name')
        team_name = form.cleaned_data.get('team_name')

        # Auto-resolve target team or generate it on the fly for this season
        team, _ = Team.objects.get_or_create(name=team_name, season=season)

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
                # Expecting CSV headers: email, first_name, last_name
                email = row.get('email', '').strip()
                first = row.get('first_name', '').strip()
                last = row.get('last_name', '').strip()
                if email:
                    self._process_coach_onboarding(email, first, last, team)

        messages.success(self.request, "Roster invitations processed. Check terminal logs!")
        return redirect('roster_onboarding', season_id=season.id)

    def _process_coach_onboarding(self, email, first_name, last_name, team):
        """Helper to seamlessly bind invitation row logic and trigger email backends."""
        # Check if an invitation token is already active for this email/team combo
        invitation, created = Invitation.objects.get_or_create(
            email=email.lower().strip(),
            team=team,
            target_role='COACH',
            invited_by=self.request.user,
            is_accepted=False
        )
        
        # Build out direct deep-link URI
        invite_url = self.request.build_absolute_uri(f"/api/profiles/invitations/verify/{invitation.token}")
        
        # Execute message compilation (Drops cleanly into console log stdout)
        send_mail(
            subject=f"Dugout Access: Join {team.name}",
            message=f"Coach {first_name} {last_name},\n\nYou have been drafted into DiamondManager for {team.name}.\nClick the link below or open the app to claim your team roster slot:\n\n{invite_url}",
            from_email='admin@diamondmanager.com',
            recipient_list=[email],
            fail_silently=False,
        )
        