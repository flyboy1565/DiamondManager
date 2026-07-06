from django import forms
from django.apps import apps
from django.contrib.auth.models import User
from .models import TeamEvent, GameLineupEntry
from leagues.models import Team, Division, Organization, Facility


SCHEDULE_EVENT_TYPE_CHOICES = [
    ('TEAM_GAME', 'Game'),
    ('TEAM_PRACTICE', 'Practice'),
    ('TEAM_SCRIMMAGE', 'Scrimmage'),
    ('TEAM_TOURNAMENT', 'Tournament'),
]


class ScheduleGameForm(forms.Form):
    """Form for scheduling a game/event between two teams in a division."""

    home_team = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        label="Home Team",
        widget=forms.Select(attrs={'class': 'w-full bg-[var(--slate-900)] border border-[var(--slate-700)] rounded-lg px-4 py-2.5 text-[var(--slate-100)] focus:outline-none focus:border-emerald-500 transition'})
    )
    away_team = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        label="Away Team",
        widget=forms.Select(attrs={'class': 'w-full bg-[var(--slate-900)] border border-[var(--slate-700)] rounded-lg px-4 py-2.5 text-[var(--slate-100)] focus:outline-none focus:border-emerald-500 transition'})
    )
    event_type = forms.ChoiceField(
        choices=SCHEDULE_EVENT_TYPE_CHOICES,
        label="Event Type",
        widget=forms.Select(attrs={'class': 'w-full bg-[var(--slate-900)] border border-[var(--slate-700)] rounded-lg px-4 py-2.5 text-[var(--slate-100)] focus:outline-none focus:border-emerald-500 transition'})
    )
    date_time = forms.DateTimeField(
        label="Date & Time",
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'w-full bg-[var(--slate-900)] border border-[var(--slate-700)] rounded-lg px-4 py-2.5 text-[var(--slate-100)] focus:outline-none focus:border-emerald-500 transition'
        })
    )
    location = forms.ModelChoiceField(
        queryset=Facility.objects.none(), required=False,
        label="Location",
        widget=forms.Select(attrs={'class': 'w-full bg-[var(--slate-900)] border border-[var(--slate-700)] rounded-lg px-4 py-2.5 text-[var(--slate-100)] focus:outline-none focus:border-emerald-500 transition'})
    )
    location_custom = forms.CharField(
        max_length=255, required=False,
        label="",
        widget=forms.TextInput(attrs={
            'placeholder': 'Or type a custom location (leave Facility empty)...',
            'class': 'w-full bg-[var(--slate-900)] border border-[var(--slate-700)] rounded-lg px-4 py-2.5 text-[var(--slate-100)] placeholder-[var(--slate-500)] focus:outline-none focus:border-emerald-500 transition'
        })
    )
    counts_against_limit = forms.BooleanField(
        required=False, initial=True,
        label="Counts against weekly limit",
        widget=forms.CheckboxInput(attrs={'class': 'rounded bg-[var(--slate-900)] border-[var(--slate-700)] text-emerald-500 focus:ring-emerald-500'})
    )

    def __init__(self, *args, division=None, **kwargs):
        super().__init__(*args, **kwargs)
        if division:
            teams = Team.objects.filter(division=division).order_by('name')
            self.fields['home_team'].queryset = teams
            self.fields['away_team'].queryset = teams
            org = division.season.organization
            self.fields['location'].queryset = Facility.objects.filter(organization=org).order_by('name', 'field_name')

    def clean(self):
        cleaned_data = super().clean()
        home = cleaned_data.get('home_team')
        away = cleaned_data.get('away_team')
        if home and away and home == away:
            raise forms.ValidationError("Home team and away team must be different.")

        location = cleaned_data.get('location')
        location_custom = cleaned_data.get('location_custom', '').strip()
        if location_custom:
            cleaned_data['location'] = location_custom
        elif location:
            cleaned_data['location'] = str(location)
        else:
            cleaned_data['location'] = ''
        return cleaned_data


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
            'status', 'counts_against_limit',
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
            'counts_against_limit': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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


DEFENSIVE_POSITION_CHOICES = [
    ('', 'Bench (no position)'),
    ('P', 'Pitcher'), ('C', 'Catcher'), ('1B', 'First Base'), ('2B', 'Second Base'),
    ('3B', 'Third Base'), ('SS', 'Shortstop'), ('LF', 'Left Field'), ('CF', 'Center Field'),
    ('RF', 'Right Field'), ('DH', 'Designated Hitter'), ('UTL', 'Utility'),
]


class LineupEntryForm(forms.Form):
    player = forms.ModelChoiceField(
        queryset=apps.get_model('profiles', 'Player').objects.none(),
        widget=forms.Select(attrs={'class': 'w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500'}),
        label="Player"
    )
    batting_order = forms.IntegerField(
        min_value=1, max_value=30,
        widget=forms.NumberInput(attrs={'class': 'w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500', 'placeholder': 'Batting order'}),
        label="Batting Order"
    )
    position = forms.ChoiceField(
        choices=DEFENSIVE_POSITION_CHOICES,
        widget=forms.Select(attrs={'class': 'w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500'}),
        required=False,
        label="Position"
    )

    def __init__(self, *args, team=None, game=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._team = team
        self._game = game
        if team:
            from profiles.models import PlayerMembership
            player_ids = PlayerMembership.objects.filter(team=team, is_active=True).values_list('player_id', flat=True)
            self.fields['player'].queryset = apps.get_model('profiles', 'Player').objects.filter(id__in=player_ids)
            self.fields['player'].label_from_instance = lambda p: f"{p.first_name} {p.last_name}"
            try:
                allowed = team.division.allowed_positions
                if allowed:
                    choices = [('', 'Bench (no position)')] + [(p, p) for p in allowed]
                    self.fields['position'].choices = choices
            except Exception:
                pass

    def clean(self):
        cleaned_data = super().clean()
        if self._team is None or self._game is None:
            return cleaned_data

        # Duplicate position is handled in the view with a confirmation dialog
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


class DivisionEventForm(forms.ModelForm):
    """
    Form for creating division-level events.
    """
    class Meta:
        model = TeamEvent
        fields = [
            'event_type', 'title', 'description', 'date_time', 'location',
            'opponent_team', 'practice_focus', 'tournament_name', 'tournament_division',
            'status', 'counts_against_limit',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Event title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location'}),
            'event_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'opponent_team': forms.Select(attrs={'class': 'form-control'}),
            'practice_focus': forms.Select(attrs={'class': 'form-control'}),
            'tournament_name': forms.TextInput(attrs={'class': 'form-control'}),
            'tournament_division': forms.TextInput(attrs={'class': 'form-control'}),
            'counts_against_limit': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, division=None, allowed_event_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.division = division
        # League-wide events don't count against weekly limits by default
        self.fields['counts_against_limit'].initial = False
        if allowed_event_types:
            event_choices = [
                (choice[0], choice[1])
                for choice in TeamEvent.EVENT_TYPE_CHOICES
                if choice[0] in allowed_event_types and 'DIVISION' in choice[0]
            ]
            self.fields['event_type'].choices = event_choices


class OrganizationEventForm(forms.ModelForm):
    """
    Form for creating organization/league-level events.
    """
    class Meta:
        model = TeamEvent
        fields = [
            'event_type', 'title', 'description', 'date_time', 'location',
            'opponent_team', 'practice_focus', 'status', 'counts_against_limit',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Event title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location'}),
            'event_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'opponent_team': forms.Select(attrs={'class': 'form-control'}),
            'practice_focus': forms.Select(attrs={'class': 'form-control'}),
            'counts_against_limit': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, organization=None, allowed_event_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        # League-wide events don't count against weekly limits by default
        self.fields['counts_against_limit'].initial = False
        if allowed_event_types:
            event_choices = [
                (choice[0], choice[1])
                for choice in TeamEvent.EVENT_TYPE_CHOICES
                if choice[0] in allowed_event_types and 'LEAGUE' in choice[0]
            ]
            self.fields['event_type'].choices = event_choices
