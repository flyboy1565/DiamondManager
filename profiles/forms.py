from django import forms
from django.contrib.auth.models import User
from django.apps import apps
from datetime import datetime

class PortalLoginForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))

class PortalOrgRegistrationForm(forms.Form):
    org_name = forms.CharField(max_length=100, label="Organization Name")
    org_city = forms.CharField(max_length=100, label="City")
    org_state = forms.CharField(max_length=2, label="State")
    org_zip__code = forms.CharField(max_length=7, label="Zip Code")
    admin_first = forms.CharField(max_length=50, label="First Name")
    admin_last = forms.CharField(max_length=50, label="Last Name")
    admin_user = forms.CharField(max_length=150, label="Username")
    admin_email = forms.EmailField(label="Contact Email")
    admin_pass = forms.CharField(widget=forms.PasswordInput(), label="Password")

    def clean_admin_user(self):
        username = self.cleaned_data.get('admin_user')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_admin_email(self):
        email = self.cleaned_data.get('admin_email').lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class OrganizationForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('leagues', 'Organization')
        fields = ['name', 'city', 'state','zip_code']

class SeasonForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.profile:
            org = user.profile.organization
            if org:
                self.fields['organization'].queryset = apps.get_model('leagues', 'Organization').objects.filter(id=org.id)
                self.fields['organization'].initial = org
            else:
                self.fields['organization'].queryset = apps.get_model('leagues', 'Organization').objects.none()
        self.fields['year'].initial = datetime.now().year
    
    class Meta:
        model = apps.get_model('leagues', 'Season')
        fields = ['organization', 'season', 'year']

class DivisionSetupForm(forms.Form):
    preset_type = forms.ChoiceField(
        label="Template",
        choices=[],
        widget=forms.RadioSelect,
        initial='CUSTOM'
    )
    selected_divisions = forms.MultipleChoiceField(
        label="Choose divisions to add",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[]
    )
    custom_name = forms.CharField(
        max_length=100,
        required=False,
        label="Custom Division Name",
        help_text="Name your custom division when using the Custom template."
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label="Division Notes",
        help_text="Optional notes for the division."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preset_type'].choices = apps.get_model('leagues', 'Division').LEAGUE_PRESETS
        blueprint_choices = []
        from leagues.league_blueprints import LEAGUE_BLUEPRINTS
        for blueprint in LEAGUE_BLUEPRINTS.values():
            for division_name in blueprint['divisions']:
                blueprint_choices.append((division_name, division_name))
        self.fields['selected_divisions'].choices = sorted(set(blueprint_choices), key=lambda item: item[0])

    def clean(self):
        cleaned_data = super().clean()
        preset_type = cleaned_data.get('preset_type')
        selected_divisions = cleaned_data.get('selected_divisions')
        custom_name = cleaned_data.get('custom_name')

        if preset_type == 'CUSTOM':
            if not custom_name:
                raise forms.ValidationError("A custom division name is required when using the Custom template.")
        else:
            if not selected_divisions:
                raise forms.ValidationError("Please choose at least one division from the selected template.")

        return cleaned_data

class RosterImportForm(forms.Form):
    division_name = forms.CharField(max_length=100, label="Division (e.g., 10U, 12U, Majors)", help_text="Will auto-create if missing")
    team_name = forms.CharField(max_length=100, label="Team Name (e.g., Bombers)")
    
    # Single manual entries
    manual_email = forms.EmailField(required=False, label="Coach Email Address")
    manual_first_name = forms.CharField(max_length=50, required=False, label="Coach First Name")
    manual_last_name = forms.CharField(max_length=50, required=False, label="Coach Last Name")
    
    # Bulk entries
    spreadsheet_file = forms.FileField(required=False, label="Upload Roster CSV (email, first_name, last_name)")

    def clean(self):
        cleaned_data = super().clean()
        manual_email = cleaned_data.get('manual_email')
        spreadsheet_file = cleaned_data.get('spreadsheet_file')

        if not manual_email and not spreadsheet_file:
            raise forms.ValidationError("You must either manually add a coach OR upload a spreadsheet roster.")
        return cleaned_data


class DivisionEditForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('leagues', 'Division')
        fields = ['name', 'preset_type', 'notes']


class TeamForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('leagues', 'Team')
        fields = ['name', 'color', 'icon']
        widgets = {
            'color': forms.TextInput(attrs={'placeholder': 'Team color or branding'}),
        }


class TeamCoachForm(forms.Form):
    user = forms.ModelChoiceField(queryset=apps.get_model('auth', 'User').objects.all(), label="User")
    role = forms.ChoiceField(choices=[('MANAGER', 'Manager'), ('COACH', 'Assistant Coach')], label="Role")


class PlayerCreateForm(forms.ModelForm):
    guardian = forms.ModelChoiceField(queryset=apps.get_model('auth', 'User').objects.all(), required=False, label="Guardian (existing user)")

    class Meta:
        model = apps.get_model('profiles', 'Player')
        fields = ['first_name', 'last_name', 'date_of_birth_field', 'guardian']


class GameCreateForm(forms.Form):
    # HTML5 datetime-local widget for browser date/time picker
    date_time = forms.DateTimeField(
        label="Date & Time",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M']
    )
    location = forms.CharField(max_length=255, widget=forms.TextInput(attrs={'placeholder': 'e.g., Main Field - Park'}))
    is_home = forms.BooleanField(required=False, initial=True, label="Is Home Game")
    opponent_team = forms.ModelChoiceField(queryset=apps.get_model('leagues', 'Team').objects.all(), required=False, label="Opponent Team (optional)")
    opponent_name = forms.CharField(max_length=200, required=False, label="Opponent Name (if not in system)")
    # Optional additional game state flags
    is_live = forms.BooleanField(required=False, initial=False, label="Start as live")
    is_completed = forms.BooleanField(required=False, initial=False, label="Mark as completed")
    current_inning = forms.IntegerField(required=False, min_value=1, initial=1)
    is_top_inning = forms.BooleanField(required=False, initial=True)
    outs = forms.IntegerField(required=False, min_value=0, initial=0)
    balls = forms.IntegerField(required=False, min_value=0, initial=0)
    strikes = forms.IntegerField(required=False, min_value=0, initial=0)