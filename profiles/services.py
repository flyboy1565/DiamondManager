from .models import Profile


def get_user_role_for_org(user, organization_id):
    """
    Checks what role a user has within a specific organization context.
    """
    if user.is_staff:
        return 'ADMIN'

    # Check if they own the org
    if Profile.objects.filter(user=user, organization_id=organization_id, role='ORG_OWNER').exists():
        return 'ORG_OWNER'

    return user.profile.role
