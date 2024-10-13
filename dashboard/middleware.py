# myapp/middleware.py
from django.utils import timezone
from pytz import timezone as pytz_timezone

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
