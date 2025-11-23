# dashboard/views/users/views_auth.py
from django.urls import reverse
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.shortcuts import redirect
from django import forms
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import get_user_model, login as dj_login
import logging
from django.conf import settings

USE_2FA = getattr(settings, "USE_TWO_FACTOR", False)
if USE_2FA:
    from django_otp import login as otp_login
    from django_otp.plugins.otp_email.models import EmailDevice
    from django_otp.plugins.otp_totp.models import TOTPDevice
else:
    # no-op shims so the module imports cleanly when 2FA is off
    def otp_login(request, device):  # noqa: N802
        return None
    EmailDevice = None
    TOTPDevice = None

# --- Import shared lockout helpers / thresholds from user_views ---
from dashboard.views.users.user_views import (
    _seconds_left, _register_failure, _clear_failures,
    _PW_LOCK_1, _PW_LOCK_2, _fail_count
)

logger = logging.getLogger("dashboard.views.users.views_auth")
User = get_user_model()

# ---------------- Helpers (no OTP imports here) ----------------

def _ip_ident(request) -> str:
    """IP-only identifier for password lockout."""
    return request.META.get('REMOTE_ADDR', '') or 'unknown'

def _post_login_redirect(request, user):
    """
    Preserve your admin vs. user routing after successful authentication.
    This is the non-2FA version (used when USE_TWO_FACTOR=False).
    """
    if request.POST.get('admin') == 'true' or request.GET.get('admin') == 'true':
        if user.is_superuser or getattr(user, 'role', None) in ['product_support','sales_rep','customer_success','implementation_rep']:
            return reverse('it_admin_dashboard')
        elif getattr(user, 'position_type', None) == 'agency_user' and getattr(user, 'agency', None):
            return reverse('agency_dashboard')
        elif hasattr(user, 'organization') and user.organization:
            return reverse('admin_dashboard', kwargs={'org_id': user.organization.id})
        return reverse('login')
    return reverse('dashboard')

# ---------------- Forms kept here so templates still import from views_auth ----------------

class Choose2FAForm(forms.Form):
    # kept for template imports; actually used by views_auth_2fa when 2FA is on
    method = forms.ChoiceField(
        choices=(('email', 'Email code'), ('totp', 'Authenticator app')),
        widget=forms.RadioSelect
    )

class TOTPForm(forms.Form):
    # kept for template imports; actually used by views_auth_2fa when 2FA is on
    token = forms.CharField(max_length=6, strip=True)

# ---------------- Lockout-aware LoginView (OTP-free) ----------------

class LockoutMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            ident = _ip_ident(request)
            wait = _seconds_left('pw', ident)
            if wait:
                username = (request.POST.get('username') or '').strip()
                return redirect(f"{request.path}?username={username}")
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        ident = _ip_ident(self.request)
        _register_failure('pw', ident, thresholds=(_PW_LOCK_1, _PW_LOCK_2))
        messages.error(self.request, "Invalid username or password.")
        username = (self.request.POST.get('username') or '').strip()
        return redirect(f"{self.request.path}?username={username}")

class RoleAwareLoginView(LockoutMixin, LoginView):
    template_name = 'auth/login.html'

    def get_success_url(self):
        # If 2FA is enabled, go to selection; otherwise go straight to home/admin
        if getattr(settings, "USE_TWO_FACTOR", False):
            return reverse('select_2fa_method')
        # get_user() is available after form_valid; we route in form_valid() instead.
        return reverse('dashboard')

    def form_valid(self, form):
        # Clear any password-failure counters for this IP
        ident = _ip_ident(self.request)
        _clear_failures('pw', ident)

        user = form.get_user()
        # Gate IT admins to the admin portal
        if getattr(user, 'position_type', None) == 'it_admin':
            messages.error(self.request, "IT Admins must log in through the Admin portal.")
            return redirect('admin_login')

        if getattr(settings, "USE_TWO_FACTOR", False):
            # 2FA handoff (do NOT call super().form_valid)
            self.request.session['pre_2fa_authenticated'] = True
            self.request.session['2fa_user_id'] = user.id
            self.request.session['2fa_admin'] = bool(
                self.request.POST.get('admin') == 'true' or self.request.GET.get('admin') == 'true'
            )
            return redirect(self.get_success_url())

        # No 2FA: finalize login now
        dj_login(self.request, user)
        target = _post_login_redirect(self.request, user)
        return redirect(target)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ident = _ip_ident(self.request)
        locked_for = _seconds_left('pw', ident)
        fails = _fail_count('pw', ident)
        attempts_left = 0 if locked_for else (max(0, _PW_LOCK_1[0] - fails) if fails > 0 else None)
        ctx['locked_for'] = locked_for
        ctx['attempts_left'] = attempts_left
        return ctx

User = get_user_model()
LOADTEST_SECRET = getattr(settings, "LOADTEST_SECRET", "super-secret-loadtest-key")


@csrf_exempt  # ok for local/loadtest only; DO NOT expose in prod
def loadtest_login(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    username = request.POST.get("username")
    secret = request.POST.get("secret")

    if not username or not secret:
        return JsonResponse({"detail": "username and secret required"}, status=400)

    if secret != LOADTEST_SECRET:
        return JsonResponse({"detail": "invalid secret"}, status=403)

    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@example.com"},
    )

    backend = getattr(
        settings,
        "AUTHENTICATION_BACKENDS",
        ["django.contrib.auth.backends.ModelBackend"],
    )[0]

    dj_login(request, user, backend=backend)

    return JsonResponse({"detail": "ok", "username": user.username})
