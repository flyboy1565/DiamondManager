"""
Permission logic for team events based on role, event type, and scope.
"""

# Event types allowed by role and scope
EVENT_PERMISSIONS = {
    'TEAM': {
        'MANAGER': ['TEAM_PRACTICE', 'TEAM_GAME', 'TEAM_SCRIMMAGE', 'TEAM_HANGOUT', 'TEAM_TOURNAMENT', 'TEAM_HOME_OPENER', 'TEAM_PARTY'],
        'COACH': ['TEAM_PRACTICE', 'TEAM_SCRIMMAGE', 'TEAM_HANGOUT', 'TEAM_TOURNAMENT'],
        'ADMIN': ['TEAM_PRACTICE', 'TEAM_GAME', 'TEAM_SCRIMMAGE', 'TEAM_HANGOUT', 'TEAM_TOURNAMENT', 'TEAM_HOME_OPENER', 'TEAM_PARTY'],
        'ORG_OWNER': ['TEAM_PRACTICE', 'TEAM_GAME', 'TEAM_SCRIMMAGE', 'TEAM_HANGOUT', 'TEAM_TOURNAMENT', 'TEAM_HOME_OPENER', 'TEAM_PARTY'],
        'ORG_ADMIN': ['TEAM_PRACTICE', 'TEAM_GAME', 'TEAM_SCRIMMAGE', 'TEAM_HANGOUT', 'TEAM_TOURNAMENT', 'TEAM_HOME_OPENER', 'TEAM_PARTY'],
    },
    'DIVISION': {
        'ADMIN': ['DIVISION_OPENING_DAY', 'DIVISION_CLOSING_CEREMONY', 'DIVISION_CHAMPIONSHIP', 'DIVISION_TOURNAMENT', 'DIVISION_CLINIC', 'DIVISION_AWARDS', 'DIVISION_ALLSTAR'],
        'ORG_OWNER': ['DIVISION_OPENING_DAY', 'DIVISION_CLOSING_CEREMONY', 'DIVISION_CHAMPIONSHIP', 'DIVISION_TOURNAMENT', 'DIVISION_CLINIC', 'DIVISION_AWARDS', 'DIVISION_ALLSTAR'],
        'ORG_ADMIN': ['DIVISION_OPENING_DAY', 'DIVISION_CLOSING_CEREMONY', 'DIVISION_CHAMPIONSHIP', 'DIVISION_TOURNAMENT', 'DIVISION_CLINIC', 'DIVISION_AWARDS', 'DIVISION_ALLSTAR'],
    },
    'ORGANIZATION': {
        'ADMIN': ['LEAGUE_OPENING_DAY', 'LEAGUE_CLOSING_CEREMONY', 'LEAGUE_TOURNAMENT', 'LEAGUE_ALLSTAR_GAME', 'LEAGUE_AWARDS', 'LEAGUE_PLAYOFF', 'LEAGUE_ANNOUNCEMENT'],
        'ORG_OWNER': ['LEAGUE_OPENING_DAY', 'LEAGUE_CLOSING_CEREMONY', 'LEAGUE_TOURNAMENT', 'LEAGUE_ALLSTAR_GAME', 'LEAGUE_AWARDS', 'LEAGUE_PLAYOFF', 'LEAGUE_ANNOUNCEMENT'],
        'ORG_ADMIN': ['LEAGUE_OPENING_DAY', 'LEAGUE_CLOSING_CEREMONY', 'LEAGUE_TOURNAMENT', 'LEAGUE_ALLSTAR_GAME', 'LEAGUE_AWARDS', 'LEAGUE_PLAYOFF', 'LEAGUE_ANNOUNCEMENT'],
    }
}


def can_create_event(user, scope, event_type, team=None, division=None, organization=None):
    """
    Check if a user can create an event of a given type at a given scope.
    """
    # Get user's role
    try:
        user_role = user.profile.role
    except:
        return False
    
    # Check if role is in permitted list for this scope and event type
    scope_permissions = EVENT_PERMISSIONS.get(scope, {})
    permitted_types = scope_permissions.get(user_role, [])
    
    if event_type not in permitted_types:
        return False
    
    # Additional checks for team-level events
    if scope == 'TEAM' and team:
        if user_role in ['MANAGER', 'COACH']:
            from profiles.models import TeamMembership
            membership = TeamMembership.objects.filter(
                user=user, 
                team=team, 
                role__in=['MANAGER', 'COACH'],
                is_active=True
            ).exists()
            return membership
    
    # Additional checks for division-level events
    if scope == 'DIVISION' and division:
        if user_role not in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
            return False
    
    # Additional checks for organization-level events
    if scope == 'ORGANIZATION' and organization:
        if user_role not in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
            return False
    
    return True


def can_edit_event(user, event):
    """
    Check if a user can edit an event.
    Admins can edit any event; creators can edit their own.
    """
    try:
        user_role = user.profile.role
    except:
        return False
    
    # Admins can edit any event
    if user_role in ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN']:
        return True
    
    # Creators can edit their own events
    return event.created_by == user


def can_delete_event(user, event):
    """
    Check if a user can delete an event.
    Same rules as editing.
    """
    return can_edit_event(user, event)


def get_allowed_event_types(user, scope, team=None, division=None, organization=None):
    """
    Get list of event types a user can create at a given scope.
    """
    try:
        user_role = user.profile.role
    except:
        return []
    
    scope_permissions = EVENT_PERMISSIONS.get(scope, {})
    return scope_permissions.get(user_role, [])


from ninja_extra import permissions as n_permissions

class IsOrgOwnerOrAdmin(n_permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        roles = list(request.user.groups.values_list('name', flat=True))
        if request.user.is_superuser or 'OWNER' in roles or 'ORG_ADMIN' in roles:
            return True
        return False

class IsGameManagerOrScorekeeper(n_permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        roles = list(request.user.groups.values_list('name', flat=True))
        if request.user.is_superuser or any(r in ('OWNER','ORG_ADMIN','TEAM_MANAGER','SCOREKEEPER') for r in roles):
            return True
        return False

class IsEventCreatorOrAdmin(n_permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        roles = list(request.user.groups.values_list('name', flat=True))
        if request.user.is_superuser or any(r in ('OWNER','ORG_ADMIN') for r in roles):
            return True
        return False

def require_team_manager_or_scorekeeper(request):
    if not request.user or not request.user.is_authenticated:
        from ninja.errors import HttpError
        raise HttpError(403, "Authentication required")
    roles = list(request.user.groups.values_list('name', flat=True))
    if request.user.is_superuser or any(r in ('OWNER','ORG_ADMIN','TEAM_MANAGER','SCOREKEEPER') for r in roles):
        return True
    from ninja.errors import HttpError
    raise HttpError(403, "Permission denied")

def require_event_creator_or_admin(request, event):
    if not request.user or not request.user.is_authenticated:
        from ninja.errors import HttpError
        raise HttpError(403, "Authentication required")
    roles = list(request.user.groups.values_list('name', flat=True))
    if request.user.is_superuser or any(r in ('OWNER','ORG_ADMIN') for r in roles):
        return True
    if event.created_by == request.user:
        return True
    from ninja.errors import HttpError
    raise HttpError(403, "Permission denied")

def can_schedule_game(request, division):
    require_team_manager_or_scorekeeper(request)
    return True

def can_manage_event(request, event):
    require_event_creator_or_admin(request, event)
    return True
