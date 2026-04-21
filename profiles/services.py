def get_user_role_for_org(user, organization_id):
    """
    Checks what role a user has within a specific organization context.
    """
    if user.is_staff:
        return 'ADMIN'
    
    # Check if they own the org
    if user.organization_set.filter(id=organization_id).exists():
        return 'ORG_OWNER'
        
    return user.profile.role