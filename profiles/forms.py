from django import forms
from django.apps import apps

class OrganizationForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('leagues', 'Organization')
        fields = ['name', 'location'] # Adjust based on your explicit fields

class SeasonForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('leagues', 'Season')
        fields = ['name', 'start_date', 'end_date', 'organization']

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