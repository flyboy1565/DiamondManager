from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from .models import TeamEvent


def get_week_range(reference_date=None):
    """
    Return (monday, sunday) for the Mon-Sun week containing reference_date.
    Monday is at 00:00:00, Sunday is at 23:59:59.999...
    """
    if reference_date is None:
        reference_date = timezone.localtime(timezone.now())
    if isinstance(reference_date, datetime):
        ref = reference_date
    else:
        ref = datetime.combine(reference_date, datetime.min.time())
        if timezone.is_aware(reference_date):
            ref = timezone.make_aware(ref)
        else:
            ref = timezone.make_aware(ref)

    monday = ref - timedelta(days=ref.weekday())
    monday_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_end = (monday_start + timedelta(days=7)) - timedelta(microseconds=1)
    return monday_start, sunday_end


def team_event_count(team, week_start=None, week_end=None):
    """
    Count of countable TeamEvent objects for a team in the given week window.
    Includes events where team is the primary team AND events where team is the opponent.
    Only counts events where counts_against_limit=True and status != 'CANCELLED'.
    """
    if week_start is None or week_end is None:
        ws, we = get_week_range()
        if week_start is None:
            week_start = ws
        if week_end is None:
            week_end = we

    return TeamEvent.objects.filter(
        Q(team=team) | Q(opponent_team=team),
        date_time__gte=week_start,
        date_time__lte=week_end,
        counts_against_limit=True,
    ).exclude(status='CANCELLED').count()


def team_can_add_events(team, count=1, week_start=None, week_end=None):
    """
    Check if the team is under its organization's weekly event limit.
    Returns (allowed, current_count, max_allowed).
    """
    ws, we = get_week_range()
    if week_start is None:
        week_start = ws
    if week_end is None:
        week_end = we

    max_allowed = team.division.season.organization.max_events_per_team_per_week
    current_count = team_event_count(team, week_start, week_end)
    allowed = (current_count + count) <= max_allowed
    return allowed, current_count, max_allowed


def get_location_conflicts(location, date_time, division, exclude_ids=None):
    """
    Find non-cancelled TeamEvent objects at the same location on the same date
    within the same division/season. Returns list of conflicting events.
    """
    if not location:
        return []

    qs = TeamEvent.objects.filter(
        location=location,
        date_time__date=date_time.date(),
        division=division,
    ).exclude(status='CANCELLED')

    if exclude_ids:
        qs = qs.exclude(id__in=exclude_ids)

    return list(qs.select_related('team', 'opponent_team').order_by('date_time'))
