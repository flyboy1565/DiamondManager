"""
Permission logic for team events based on role and event type.
"""

EVENT_PERMISSIONS = {
    'OPENING_DAY': ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
    'CLOSING_CEREMONY': ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
    'GAME': ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
    'TOURNAMENT': ['ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
    'PRACTICE': ['MANAGER', 'COACH', 'ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
    'SCRIMMAGE': ['MANAGER', 'COACH', 'ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
    'HANGOUT': ['MANAGER', 'COACH', 'ADMIN', 'ORG_OWNER', 'ORG_ADMIN'],
}


def can_create_event(user, team, event_type):
    """
    Check if a user can create an event of a given type for a team.
    """
    # Get user's role (from profile)
    try:
        user_role = user.profile.role
    except:
        return False
    
    # Check if role is in permitted list for this event type
    permitted_roles = EVENT_PERMISSIONS.get(event_type, [])
    if user_role not in permitted_roles:
        return False
    
    # Additional check: For non-admin roles, verify they're a coach/manager on this team
    if user_role in ['MANAGER', 'COACH']:
        from profiles.models import TeamMembership
        membership = TeamMembership.objects.filter(
            user=user, 
            team=team, 
            role__in=['MANAGER', 'COACH'],
            is_active=True
        ).exists()
        return membership
    
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


def get_allowed_event_types(user, team):
    """
    Get list of event types a user can create for a team.
    """
    allowed = []
    for event_type in EVENT_PERMISSIONS.keys():
        if can_create_event(user, team, event_type):
            allowed.append(event_type)
    return allowed
