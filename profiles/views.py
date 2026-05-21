import csv
import io
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.core.mail import send_mail

from leagues.models import Team, Season  # Assuming where leagues apps reside
from .models import Profile, Invitation, Player
from .forms import OrganizationForm, SeasonForm, RosterImportForm

# 1. STEP ONE: INITIALIZE ORGANIZATION
class CreateOrganizationView(LoginRequiredMixin, CreateView):
    template_name = 'profiles/admin/create_org.html'
    form_class = OrganizationForm
    success_url = reverse_lazy('create_season')

    def form_valid(self, form):
        # Automatically make the creator the owner
        response = super().form_valid(self.object)
        profile = self.request.user.profile
        profile.role = 'ORG_OWNER'
        profile.save()
        # Associate user with the org if your model has an explicit field/M2M
        # self.object.owners.add(self.request.user)
        messages.success(self.request, "Organization established successfully!")
        return response

# 2. STEP TWO: SPAWN A SEASON
class CreateSeasonView(LoginRequiredMixin, CreateView):
    template_name = 'profiles/admin/create_season.html'
    form_class = SeasonForm

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