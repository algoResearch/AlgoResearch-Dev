# myapp/middleware.py
from django.utils import timezone
from pytz import timezone as pytz_timezone
from django.shortcuts import redirect


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'timezone'):
            user_timezone = request.user.timezone  # Assume `timezone` field in User model
            timezone.activate(pytz_timezone(user_timezone))
        else:
            timezone.deactivate()

        response = self.get_response(request)
        return response
    
class RoleBasedRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path == '/accounts/profile/':
            if request.user.role in ['admin', 'principal_admin']:
                print(f"Redirecting {request.user.username} to admin dashboard.")
                return redirect('admin_dashboard', org_id=request.user.organization.id)
            else:
                print(f"Redirecting {request.user.username} to regular dashboard.")
                return redirect('dashboard', org_id=request.user.organization.id)
        return self.get_response(request)
class OrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.organization = request.user.organization
        else:
            request.organization = None
        response = self.get_response(request)
        return response
