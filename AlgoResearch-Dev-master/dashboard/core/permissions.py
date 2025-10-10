from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from ..models import Organization, Cage, Animal

def check_organization_access(user, org_id):
    """
    Checks if the user belongs to the given organization.
    """
    return user.organization_id == org_id

def check_admin_access(user, org_id):
    """
    Allows access to Admins and Principal Admins of the organization.
    """
    return user.role in ['admin', 'principal_admin'] and user.organization_id == org_id

def check_cage_access(user, cage_id):
    """
    Allows access to users assigned to the cage or its animals.
    """
    cage = get_object_or_404(Cage, id=cage_id)
    if user.role in ['admin', 'principal_admin'] and user.organization_id == cage.organization_id:
        return True
    return cage.animals.filter(assigned_users=user).exists()

def check_animal_access(user, animal_id):
    """
    Allows access to users assigned to the animal.
    """
    animal = get_object_or_404(Animal, id=animal_id)
    if user.role in ['admin', 'principal_admin'] and user.organization_id == animal.cage.organization_id:
        return True
    return user in animal.assigned_users.all()

def ensure_access(condition, error_message="You do not have permission to access this resource."):
    """
    A decorator or utility to enforce access checks.
    """
    if not condition:
        return HttpResponseForbidden(error_message)
