# myapp/middleware.py
from django.utils import timezone, translation
from pytz import timezone as pytz_timezone
from django.conf import settings
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
    


class UserLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'language'):
            translation.activate(request.user.language)
            request.session[settings.LANGUAGE_COOKIE_NAME] = request.user.language
        return self.get_response(request)
    
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
