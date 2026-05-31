from django import forms
from django.contrib.auth.models import User
from .models import TeamEvent
from leagues.models import Team


class TeamEventForm(forms.ModelForm):
    """
    Dynamic form for creating/editing team events.
    Fields shown depend on event_type.
    """
    
    class Meta:
        model = TeamEvent
        fields = [
            'event_type', 'title', 'description', 'date_time', 'location',
            'opponent_team', 'is_home_game',
            'practice_focus', 'attendance_required',
            'tournament_name', 'tournament_division',
            'status'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Event title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location'}),
            'event_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'opponent_team': forms.Select(attrs={'class': 'form-control'}),
            'is_home_game': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'practice_focus': forms.Select(attrs={'class': 'form-control'}),
            'attendance_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tournament_name': forms.TextInput(attrs={'class': 'form-control'}),
            'tournament_division': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, team=None, allowed_event_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        
        # Restrict event types if specified
        if allowed_event_types:
            event_choices = [
                (choice[0], choice[1]) 
                for choice in TeamEvent.EVENT_TYPE_CHOICES 
                if choice[0] in allowed_event_types
            ]
            self.fields['event_type'].choices = event_choices
        
        # Restrict opponent team to other teams in same division
        if team:
            from leagues.models import Division
            try:
                division = team.division
                other_teams = Team.objects.filter(division=division).exclude(id=team.id)
                self.fields['opponent_team'].queryset = other_teams
            except:
                self.fields['opponent_team'].queryset = Team.objects.none()
    
    def clean(self):
        cleaned_data = super().clean()
        event_type = cleaned_data.get('event_type')
        
        # Hide/validate fields based on event type
        if event_type not in ['GAME', 'SCRIMMAGE']:
            cleaned_data['opponent_team'] = None
            cleaned_data['is_home_game'] = None
        
        if event_type != 'PRACTICE':
            cleaned_data['practice_focus'] = None
            cleaned_data['attendance_required'] = False
        
        if event_type != 'TOURNAMENT':
            cleaned_data['tournament_name'] = None
            cleaned_data['tournament_division'] = None
        
        return cleaned_data


class GameScoreForm(forms.Form):
    """
    Form for recording game scores after event completion.
    """
    home_score = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Home Score'})
    )
    away_score = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Away Score'})
    )
    status = forms.ChoiceField(
        choices=[('COMPLETED', 'Mark as Completed')],
        widget=forms.HiddenInput(),
        initial='COMPLETED'
    )
