from django import forms
from django.contrib.auth.models import User
from django.apps import apps
from datetime import datetime

class PortalLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'})
    )


class PortalOrgRegistrationForm(forms.Form):
    # Organization Data Fields
    org_name = forms.CharField(
        max_length=100, 
        label="Organization Name"
    )
    org_city = forms.CharField(
        max_length=100, 
        label="City"
    )
    org_state = forms.CharField(
        max_length=2, 
        label="State"
    )
    org_zip__code = forms.CharField(
        max_length=7, 
        label="Zip Code"
    )
    
    # Primary Administrator Account Data Fields
    admin_first = forms.CharField(max_length=50, label="First Name")
    admin_last = forms.CharField(max_length=50, label="Last Name")
    admin_user = forms.CharField(max_length=150, label="Username")
    admin_email = forms.EmailField(label="Contact Email")
    admin_pass = forms.CharField(
        widget=forms.PasswordInput(), 
        label="Password"
    )

    def clean_admin_user(self):
        """Ensure the administrator username hasn't already been claimed."""
        username = self.cleaned_data.get('admin_user')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_admin_email(self):
        """Ensure the administrator email isn't already tied to an account."""
        email = self.cleaned_data.get('admin_email').lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class OrganizationForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('leagues', 'Organization')
        fields = ['name', 'city', 'state','zip_code'] # Adjust based on your explicit fields

class SeasonForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter organizations to only those owned by the user
        if user and user.profile:
            org = user.profile.organization
            if org:
                self.fields['organization'].queryset = apps.get_model('leagues', 'Organization').objects.filter(id=org.id)
                # Pre-select the user's organization
                self.fields['organization'].initial = org
            else:
                # If user has no organization, show empty queryset
                self.fields['organization'].queryset = apps.get_model('leagues', 'Organization').objects.none()
        
        # Pre-select current year
        self.fields['year'].initial = datetime.now().year
    
    class Meta:
        model = apps.get_model('leagues', 'Season')
        fields = ['organization', 'season', 'year']

class RosterImportForm(forms.Form):
    # Mapping Context
    team_name = forms.CharField(max_length=100, label="Team Name (e.g., 12U Bombers)")
    
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